"""Queues (doc 12) — A1: chain sequencing. `Bus.chain` runs each link only after the prior
succeeds; a failure stops the chain (running `catch` if set) rather than continuing. Replaces the
old push-all-at-once loop, which ran every link concurrently."""

from __future__ import annotations

from typing import Any

from taskiq import InMemoryBroker

from arvel.kernel import Application, set_application
from arvel.queue import Bus, Job, QueueManager, queue_callback

ORDER: list[str] = []
CAUGHT: list[BaseException] = []


class Ok(Job):
    def __init__(self, label: str) -> None:
        self.label = label

    async def handle(self) -> None:
        ORDER.append(self.label)


class Boom(Job):
    tries = 1  # fail on the first (and only) attempt -> exhausted immediately

    def __init__(self, label: str) -> None:
        self.label = label

    async def handle(self) -> None:
        ORDER.append(self.label)
        raise ValueError("boom")

    async def failed(self, exc: BaseException) -> None:
        """Silence: this test asserts on `catch`/ORDER, not on FailedJob persistence noise."""


@queue_callback
def _record_catch(exc: BaseException) -> None:
    CAUGHT.append(exc)


async def _manager() -> QueueManager:
    # await_inplace=True: each `kiq()` runs its job fully before returning, so the whole chain
    # (a cascade of pushes from within `_dispatch_next_link`) completes synchronously — no polling.
    app = Application()
    manager = QueueManager(app, broker=InMemoryBroker(await_inplace=True))
    app.instance("queue", manager)
    set_application(app)
    return manager


async def test_chain_runs_strictly_in_order() -> None:
    ORDER.clear()
    manager = await _manager()
    try:
        await Bus.chain([Ok("a"), Ok("b"), Ok("c")]).dispatch(manager=manager)
        assert ORDER == ["a", "b", "c"]
    finally:
        set_application(None)


async def test_chain_stops_after_a_middle_failure_and_runs_catch() -> None:
    ORDER.clear()
    CAUGHT.clear()
    manager = await _manager()
    try:
        await (
            Bus.chain([Ok("a"), Boom("b"), Ok("c")]).catch(_record_catch).dispatch(manager=manager)
        )
        assert ORDER == ["a", "b"]  # "c" never runs
        assert len(CAUGHT) == 1
        assert isinstance(CAUGHT[0], ValueError)
    finally:
        set_application(None)


class RecordingManager:
    """A spy standing in for the queue manager — proves `PendingChain.dispatch` pushes only the
    head job now (the rest travel serialized on it), not every link at once."""

    def __init__(self) -> None:
        self.pushed: list[Any] = []

    async def push_instance(self, job: Any, *, queue: str | None = None) -> Any:
        self.pushed.append(job)
        return job


async def test_chain_dispatch_pushes_only_the_head_job() -> None:
    rec = RecordingManager()
    a, b, c = Ok("a"), Ok("b"), Ok("c")
    await Bus.chain([a, b, c]).dispatch(manager=rec)
    assert rec.pushed == [a]  # b/c aren't pushed yet — they travel serialized on `a`
    assert len(a.__arvel_chain__) == 2
