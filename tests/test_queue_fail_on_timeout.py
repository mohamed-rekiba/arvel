"""E14/V1 — `Job.fail_on_timeout`: a timed-out attempt normally retries like any other failure
(`test_queue_timeout.py`); with `fail_on_timeout=True` the **first** timeout gives up immediately
instead — `failed()` runs, a `FailedJob` is recorded, no retry. A non-timeout exception is
unaffected by the flag either way. Test-first (spec E14 acceptance criteria)."""

from __future__ import annotations

import asyncio

import sqlalchemy as sa
from taskiq import InMemoryBroker

from arvel.database import ConnectionResolver
from arvel.kernel import Application, set_application
from arvel.queue import FailedJob, Job, QueuedJob, QueueManager, run_job_with_retries


async def _no_sleep(_delay: float) -> None:
    return None


class SlowOnce(Job):
    """Never finishes inside its `timeout` — every attempt times out."""

    tries = 3
    backoff = 0
    timeout = 0.05
    fail_on_timeout = True

    def __init__(self) -> None:
        self.started = 0
        self.failed_with: BaseException | None = None

    async def handle(self) -> None:
        self.started += 1
        await asyncio.sleep(10)

    async def failed(self, exc: BaseException) -> None:
        self.failed_with = exc


async def test_fail_on_timeout_true_gives_up_on_the_first_timeout_no_retry() -> None:
    job = SlowOnce()
    result = await run_job_with_retries(job, sleep=_no_sleep)
    assert result is None
    assert job.started == 1  # only one attempt ran — no retry despite tries=3
    assert isinstance(job.failed_with, TimeoutError)  # failed() got the timeout, not a stand-in


class SlowRetriesByDefault(Job):
    """Same shape as `SlowOnce` but `fail_on_timeout` left at its `False` default — must behave
    exactly like a plain timeout (see `test_queue_timeout.py`): retried up to `tries`."""

    tries = 3
    backoff = 0
    timeout = 0.05

    def __init__(self) -> None:
        self.started = 0
        self.failed_with: BaseException | None = None

    async def handle(self) -> None:
        self.started += 1
        await asyncio.sleep(10)

    async def failed(self, exc: BaseException) -> None:
        self.failed_with = exc


async def test_fail_on_timeout_false_retries_a_timeout_up_to_tries_unchanged() -> None:
    job = SlowRetriesByDefault()
    assert job.fail_on_timeout is False
    await run_job_with_retries(job, sleep=_no_sleep)
    assert job.started == 3  # every attempt ran — the flag-off path is the pre-existing behavior
    assert isinstance(job.failed_with, TimeoutError)


class FailOnTimeoutButThrowsInstead(Job):
    """`fail_on_timeout=True` must only special-case `TimeoutError` — a regular exception still
    retries up to `tries`, unaffected by the flag."""

    tries = 3
    backoff = 0
    fail_on_timeout = True

    def __init__(self) -> None:
        self.attempts = 0

    async def handle(self) -> None:
        self.attempts += 1
        raise ValueError("not a timeout")

    async def failed(self, exc: BaseException) -> None: ...


async def test_fail_on_timeout_does_not_affect_a_non_timeout_exception() -> None:
    job = FailOnTimeoutButThrowsInstead()
    await run_job_with_retries(job, sleep=_no_sleep)
    assert job.attempts == 3  # the full `tries` ran — a generic failure is not a timeout


class DurableSlowJob(Job):
    tries = 3
    backoff = 0
    timeout = 0.05

    async def handle(self) -> None:
        await asyncio.sleep(10)


class DurableSlowJobFailFast(DurableSlowJob):
    fail_on_timeout = True


async def _setup() -> tuple[QueueManager, ConnectionResolver]:
    app = Application()
    db = ConnectionResolver()
    app.instance("db", db)
    # await_inplace=True: deterministic (no polling); a real broker still round-trips through the
    # same `jobs` table release/redispatch mechanics (see the AMQP integration test / DR-0048).
    manager = QueueManager(app, broker=InMemoryBroker(await_inplace=True))
    app.instance("queue", manager)
    set_application(app)
    QueuedJob.set_connection(db)
    FailedJob.set_connection(db)
    await db.execute(sa.schema.CreateTable(QueuedJob.__table__))
    await db.execute(sa.schema.CreateTable(FailedJob.__table__))
    return manager, db


async def test_durable_rail_fail_on_timeout_true_fails_on_first_timeout_not_released() -> None:
    manager, db = await _setup()
    try:
        await manager.push_instance(DurableSlowJobFailFast())
        failed = await FailedJob.all()
        assert len(failed) == 1  # recorded on the very first timeout
        assert "TimeoutError" in failed[0].exception
        assert await QueuedJob.all() == []  # never released for a retry
    finally:
        set_application(None)
        await db.dispose()


async def test_durable_rail_fail_on_timeout_false_releases_for_retry_unchanged() -> None:
    manager, db = await _setup()
    try:
        await manager.push_instance(DurableSlowJob())
        rows = await QueuedJob.all()
        assert len(rows) == 1  # released back to the jobs table, exactly like any other failure
        assert rows[0].attempts == 1
        assert await FailedJob.all() == []  # not failed yet — tries=3 not exhausted
    finally:
        set_application(None)
        await db.dispose()
