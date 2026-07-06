"""After-commit dispatch through the one deferral seam: db.transaction() wraps the events
buffer, and both after-commit events and after-commit jobs ride it — flushed on commit,
dropped on rollback, immediate outside a transaction."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from arvel.database.connections import ConnectionResolver
from arvel.events import Dispatcher, ShouldDispatchAfterCommit
from arvel.kernel.application import Application
from arvel.kernel.globals import set_application
from arvel.queue import Job, QueueManager
from arvel.queue.middleware import ShouldBeUnique

RAN: list[str] = []


class DeferredJob(Job):
    after_commit = True

    def __init__(self, value: str) -> None:
        self.value = value

    async def handle(self) -> None:
        RAN.append(self.value)


class EagerJob(Job):
    def __init__(self, value: str) -> None:
        self.value = value

    async def handle(self) -> None:
        RAN.append(self.value)


class OnceJob(ShouldBeUnique, Job):
    # module-level so the broker can re-import it by path
    after_commit = True

    def __init__(self, value: str) -> None:
        self.value = value

    async def handle(self) -> None:
        RAN.append(self.value)


class Shipped(ShouldDispatchAfterCommit):
    def __init__(self, n: int) -> None:
        self.n = n


class Boom(Exception):
    pass


async def _drain() -> None:
    """Give the in-memory broker's scheduled task a few loop turns to run. 20 turns is a
    ceiling, not a sleep: the handlers here are pure-memory appends, done in one or two."""
    for _ in range(20):
        await asyncio.sleep(0)


@pytest.fixture
async def ctx() -> Any:
    RAN.clear()
    app = Application()
    events = Dispatcher()
    manager = QueueManager()
    app.instance("events", events)
    app.instance("queue", manager)
    set_application(app)
    db = ConnectionResolver({"default": {"url": "sqlite+aiosqlite://"}})
    try:
        yield app, events, db
    finally:
        set_application(None)
        if manager._started:
            await manager.broker.shutdown()
        await db.dispose()


async def test_after_commit_job_waits_for_commit(ctx: Any) -> None:
    _, _, db = ctx
    async with db.transaction():
        assert await DeferredJob.dispatch("deferred") is None  # deferred → no broker task yet
        await _drain()
        assert RAN == []  # the broker must not see the job while the tx is open
    await _drain()
    assert RAN == ["deferred"]


async def test_after_commit_job_dropped_on_rollback(ctx: Any) -> None:
    _, _, db = ctx
    with pytest.raises(Boom):
        async with db.transaction():
            await DeferredJob.dispatch("doomed")
            raise Boom
    await _drain()
    assert RAN == []


async def test_after_commit_job_outside_transaction_is_immediate(ctx: Any) -> None:
    task = await DeferredJob.dispatch("now")
    assert task is not None  # immediate path still returns the broker task
    await task.wait_result()
    assert RAN == ["now"]


async def test_nested_transactions_defer_to_outermost_commit(ctx: Any) -> None:
    _, _, db = ctx
    async with db.transaction():
        async with db.transaction():  # savepoint
            await DeferredJob.dispatch("inner")
        await _drain()
        assert RAN == []  # savepoint release is not a commit
    await _drain()
    assert RAN == ["inner"]


async def test_dispatch_after_commit_wins_over_class_default(ctx: Any) -> None:
    _, _, db = ctx
    async with db.transaction():
        await EagerJob.dispatch_after_commit("forced")  # class default is immediate
        await _drain()
        assert RAN == []
    await _drain()
    assert RAN == ["forced"]


async def test_plain_job_inside_transaction_stays_immediate(ctx: Any) -> None:
    _, _, db = ctx
    async with db.transaction():
        task = await EagerJob.dispatch("eager")
        await task.wait_result()
        assert RAN == ["eager"]  # no opt-in, no deferral — documented posture


async def test_unique_deferred_job_enqueues_once_at_flush(ctx: Any) -> None:
    # the unique gate runs at flush (not at dispatch), so work that may roll back never
    # reserves the lock — and a double dispatch in one tx still enqueues exactly once
    from arvel.cache.provider import CacheServiceProvider

    app, _, db = ctx
    CacheServiceProvider(app).register()  # the unique lock lives in the cache

    async with db.transaction():
        await OnceJob.dispatch("once")
        await OnceJob.dispatch("once")
        await _drain()
        assert RAN == []
    await _drain()
    assert RAN == ["once"]


async def test_after_commit_events_defer_inside_db_transaction(ctx: Any) -> None:
    # the seam regression: db.transaction() itself must buffer after-commit EVENTS —
    # no manual events.transaction() composition by the app
    _, events, db = ctx
    fired: list[int] = []
    events.listen(Shipped, lambda e: fired.append(e.n))
    async with db.transaction():
        await events.dispatch(Shipped(1))
        assert fired == []
    assert fired == [1]


async def test_after_commit_events_drop_on_db_rollback(ctx: Any) -> None:
    _, events, db = ctx
    fired: list[int] = []
    events.listen(Shipped, lambda e: fired.append(e.n))
    with pytest.raises(Boom):
        async with db.transaction():
            await events.dispatch(Shipped(2))
            raise Boom
    assert fired == []
