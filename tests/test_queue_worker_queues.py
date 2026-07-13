"""Queues (5.2) — `QueueManager.work(queues=[...])` actually filters + prioritizes.

Uses the memory broker + the durable `jobs` table (delayed dispatch), mirroring
`test_queue_worker_flags.py`'s pattern: the in-memory broker runs a job inline once released, so
the *ordering* this exercises is `release_due_jobs`'s own queue-priority cadence, not the broker's.
"""

from __future__ import annotations

import asyncio

import sqlalchemy as sa
from taskiq import InMemoryBroker

from arvel.database import ConnectionResolver
from arvel.kernel import Application, set_application
from arvel.queue import Job, QueuedJob, QueueManager

PROCESSED: list[str] = []


class Tick(Job):
    def __init__(self, name: str) -> None:
        self.name = name

    async def handle(self) -> None:
        PROCESSED.append(self.name)


async def _setup() -> tuple[QueueManager, ConnectionResolver]:
    PROCESSED.clear()
    app = Application()
    db = ConnectionResolver()
    app.instance("db", db)
    manager = QueueManager(app, broker=InMemoryBroker())
    app.instance("queue", manager)
    set_application(app)
    QueuedJob.set_connection(db)
    await db.execute(sa.schema.CreateTable(QueuedJob.__table__))
    return manager, db


async def test_work_queues_filters_unlisted_queues_to_a_clean_empty_poll() -> None:
    manager, db = await _setup()
    try:
        await manager.dispatch_after(0, Tick("wanted"), queue="high")
        await manager.dispatch_after(0, Tick("ignored"), queue="unlisted")
        await asyncio.wait_for(
            manager.work(queues=["high"], release_interval=0.02, stop_when_empty=True),
            timeout=5,
        )
        assert PROCESSED == ["wanted"]  # "unlisted" never ran
    finally:
        set_application(None)
        await db.dispose()


async def test_work_queues_releases_in_the_given_priority_order() -> None:
    manager, db = await _setup()
    try:
        # dispatched low-to-high; released order must follow the `queues=` priority, not this one
        await manager.dispatch_after(0, Tick("low"), queue="low")
        await manager.dispatch_after(0, Tick("default"), queue="default")
        await manager.dispatch_after(0, Tick("high"), queue="high")
        await asyncio.wait_for(
            manager.work(
                queues=["high", "default", "low"], release_interval=0.02, stop_when_empty=True
            ),
            timeout=5,
        )
        assert PROCESSED == ["high", "default", "low"]
    finally:
        set_application(None)
        await db.dispose()


async def test_direct_invoke_drops_a_job_on_a_queue_this_worker_does_not_consume() -> None:
    """The defensive receive-time filter (`_invoke`) — the safety net for any broker that can't
    filter at the network level (or an in-process dispatch bypassing the jobs table entirely)."""
    from arvel.queue import _WorkerOptions  # pyright: ignore[reportPrivateUsage]

    manager, db = await _setup()
    manager._worker._worker_options = _WorkerOptions(
        max_jobs=None, rest=0.0, stop_when_empty=False, queues=["high"]
    )
    try:
        result = await manager._worker._invoke(Tick("skipped"))
        assert result is None
        assert PROCESSED == []
    finally:
        manager._worker._worker_options = None
        set_application(None)
        await db.dispose()


async def test_filtered_delivery_without_a_db_runs_rather_than_drops() -> None:
    """No durable store and no other consumer (the inline broker is the sole executor) — an
    already-acked filtered delivery must run here, not vanish (DR-0049)."""
    from arvel.queue import _WorkerOptions  # pyright: ignore[reportPrivateUsage]

    PROCESSED.clear()
    app = Application()  # deliberately no "db" binding
    manager = QueueManager(app, broker=InMemoryBroker())
    app.instance("queue", manager)
    set_application(app)
    manager._worker._worker_options = _WorkerOptions(
        max_jobs=None, rest=0.0, stop_when_empty=False, queues=["emails"]
    )
    try:
        await manager._worker._invoke(Tick("stray"), queue_label="reports")
        assert PROCESSED == ["stray"]  # run, not dropped — nothing durable to park into
    finally:
        manager._worker._worker_options = None
        set_application(None)


async def test_work_without_queues_still_consumes_everything() -> None:
    manager, db = await _setup()
    try:
        await manager.dispatch_after(0, Tick("a"), queue="one")
        await manager.dispatch_after(0, Tick("b"), queue="two")
        await asyncio.wait_for(manager.work(release_interval=0.02, stop_when_empty=True), timeout=5)
        assert set(PROCESSED) == {"a", "b"}
    finally:
        set_application(None)
        await db.dispose()


async def test_filtered_broker_delivery_is_parked_not_lost() -> None:
    """A queue-filtering worker receiving a job for a queue it doesn't consume must park
    it durably (jobs table) for another worker — the broker acks the delivery either way."""
    from arvel.queue import _WorkerOptions  # pyright: ignore[reportPrivateUsage]

    manager, db = await _setup()
    try:
        manager._worker._worker_options = _WorkerOptions(
            max_jobs=None, rest=0.0, stop_when_empty=False, queues=["emails"]
        )
        result = await manager._worker._invoke(Tick("stray"), queue_label="reports")
        assert result is None
        assert PROCESSED == []  # not executed by this worker
        parked = await QueuedJob.get()
        assert len(parked) == 1 and parked[0].queue == "reports"  # durable, not lost
    finally:
        manager._worker._worker_options = None
        set_application(None)
        await db.dispose()
