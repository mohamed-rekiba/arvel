"""Queues (doc 12) — B1: retry-release. A failing job on a durable (DB-bound) queue is released
back with a future `available_at` instead of an inline `asyncio.sleep`; attempts increment across
worker passes (persisted on the job row, carried via `Job.__arvel_attempts__`), and the worker is
never blocked waiting out the backoff."""

from __future__ import annotations

import time

import sqlalchemy as sa
from taskiq import InMemoryBroker

from arvel.database import ConnectionResolver
from arvel.kernel import Application, set_application
from arvel.queue import Job, QueuedJob, QueueManager

ATTEMPTS: list[int] = []
DRAINED: list[str] = []


class FlakyTwice(Job):
    """Fails on attempts 1 and 2, succeeds on 3 — a big `backoff` proves release-not-sleep: an
    inline `asyncio.sleep(backoff)` would make this test visibly slow (and block a concurrent job)."""

    tries = 3
    backoff = 30

    def __init__(self) -> None:
        self.calls = 0

    async def handle(self) -> None:
        self.calls += 1
        ATTEMPTS.append(self.calls)
        if self.calls < 3:
            raise ValueError("not yet")


class Other(Job):
    async def handle(self) -> None:
        DRAINED.append("other")


async def _setup() -> tuple[QueueManager, ConnectionResolver]:
    ATTEMPTS.clear()
    DRAINED.clear()
    app = Application()
    db = ConnectionResolver()
    app.instance("db", db)
    # await_inplace=True: deterministic (no polling); a real broker still round-trips through the
    # same `jobs` table release/redispatch mechanics (see the AMQP integration test).
    manager = QueueManager(app, broker=InMemoryBroker(await_inplace=True))
    app.instance("queue", manager)
    set_application(app)
    QueuedJob.set_connection(db)
    await db.execute(sa.schema.CreateTable(QueuedJob.__table__))
    return manager, db


async def test_failed_attempt_releases_with_future_available_at_no_inline_sleep() -> None:
    manager, db = await _setup()
    try:
        job = FlakyTwice()
        started = time.monotonic()
        await manager.push_instance(job)
        elapsed = time.monotonic() - started
        assert elapsed < 5, "release blocked inline for (part of) the 30s backoff"
        assert ATTEMPTS == [1]  # exactly one attempt this pass — no in-loop retry

        rows = await QueuedJob.all()
        assert len(rows) == 1
        assert rows[0].attempts == 1
        assert rows[0].available_at > int(time.time())  # released into the future, not immediate

        # a second, unrelated job drains right away — not queued behind the first job's backoff
        await manager.push_instance(Other())
        assert DRAINED == ["other"]

        # simulate the backoff having elapsed: release_due_jobs redispatches -> attempt 2 (fails again)
        released = await manager.release_due_jobs(now=rows[0].available_at)
        assert released == 1
        assert ATTEMPTS == [1, 2]
        rows = await QueuedJob.all()
        assert len(rows) == 1
        assert rows[0].attempts == 2

        # attempt 3 succeeds -> no further release, the row is gone
        released = await manager.release_due_jobs(now=rows[0].available_at)
        assert released == 1
        assert await QueuedJob.all() == []
        assert ATTEMPTS == [1, 2, 3]
    finally:
        set_application(None)
        await db.dispose()


async def test_in_memory_without_db_falls_back_to_inline_retry() -> None:
    """Documented fallback: no DB bound -> the classic inline loop (all attempts in one pass)."""
    app = Application()
    manager = QueueManager(app, broker=InMemoryBroker(await_inplace=True))
    app.instance("queue", manager)
    set_application(app)
    try:
        ATTEMPTS.clear()
        job = FlakyTwice()
        job.backoff = 0  # keep the inline loop instant
        await manager.push_instance(job)
        assert ATTEMPTS == [1, 2, 3]  # all three attempts ran inline, in this one call
    finally:
        set_application(None)
