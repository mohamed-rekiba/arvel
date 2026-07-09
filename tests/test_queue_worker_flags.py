"""Queues (doc 12) — worker lifecycle flags: `--max-jobs`/`--max-time`/`--stop-when-empty`/`--rest`
terminate (or pace) the `work()` loop correctly; a stop event (what SIGTERM/SIGINT wires up)
ends the run gracefully. Real signal delivery + a real broker's cooperative drain-in-flight-work
is exercised by the AMQP integration test; this covers the loop-termination logic itself."""

from __future__ import annotations

import asyncio
import time

import sqlalchemy as sa
from taskiq import InMemoryBroker

from arvel.database import ConnectionResolver
from arvel.kernel import Application, set_application
from arvel.queue import Job, QueuedJob, QueueManager

PROCESSED: list[int] = []


class Tick(Job):
    def __init__(self, n: int) -> None:
        self.n = n

    async def handle(self) -> None:
        PROCESSED.append(self.n)


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


async def test_max_jobs_stops_the_worker_after_n_processed() -> None:
    manager, db = await _setup()
    try:
        for n in range(3):
            await manager.dispatch_after(0, Tick(n))  # due immediately
        await asyncio.wait_for(manager.work(release_interval=0.02, max_jobs=2), timeout=5)
        assert len(PROCESSED) >= 2  # stopped once max_jobs was reached
    finally:
        set_application(None)
        await db.dispose()


async def test_stop_when_empty_stops_once_idle() -> None:
    manager, db = await _setup()
    try:
        await manager.dispatch_after(0, Tick(1))
        await asyncio.wait_for(manager.work(release_interval=0.02, stop_when_empty=True), timeout=5)
        assert PROCESSED == [1]
    finally:
        set_application(None)
        await db.dispose()


async def test_max_time_stops_the_worker_after_the_given_seconds() -> None:
    manager, db = await _setup()
    try:
        started = time.monotonic()
        await asyncio.wait_for(manager.work(release_interval=0.05, max_time=0.1), timeout=5)
        assert time.monotonic() - started >= 0.1
    finally:
        set_application(None)
        await db.dispose()


async def test_rest_pauses_after_each_job() -> None:
    """`rest` pauses after each job. Checked directly against `_invoke`'s own
    timing rather than `work()`'s overall wall time: the in-memory broker runs each dispatched job
    as its own independent background task (no real single-consumer loop for a whole-worker
    measurement to serialize against) — a real Receiver-consumed broker's actual pacing is covered
    by the AMQP integration test."""
    from arvel.queue import _WorkerOptions  # pyright: ignore[reportPrivateUsage]

    manager, db = await _setup()
    manager._worker._worker_options = _WorkerOptions(max_jobs=None, rest=0.2, stop_when_empty=False)
    try:
        started = time.monotonic()
        await manager._worker._invoke(Tick(1))
        assert time.monotonic() - started >= 0.2
        assert PROCESSED == [1]
    finally:
        manager._worker._worker_options = None
        set_application(None)
        await db.dispose()


async def test_stop_event_ends_the_run_gracefully() -> None:
    """What a SIGTERM/SIGINT handler does (``finish.set()``) makes `work()` return promptly."""
    manager, db = await _setup()
    try:
        task = asyncio.create_task(manager.work(release_interval=0.02))
        for _ in range(50):
            if manager._worker._worker_stop is not None:
                break
            await asyncio.sleep(0.01)
        assert manager._worker._worker_stop is not None
        manager._worker._worker_stop.set()
        await asyncio.wait_for(task, timeout=5)
    finally:
        set_application(None)
        await db.dispose()
