"""Queues (doc 12) — visibility timeout: a `jobs` row reserved by a worker that died before
finishing (claimed via `reserved_at`, never deleted) is reclaimed once `retry_after` has passed and
picked up by another pass, instead of leaking forever."""

from __future__ import annotations

import time

import sqlalchemy as sa
from taskiq import InMemoryBroker

from arvel.database import ConnectionResolver
from arvel.kernel import Application, set_application
from arvel.queue import Job, QueuedJob, QueueManager

RAN: list[str] = []


class Greet(Job):
    def __init__(self, who: str) -> None:
        self.who = who

    async def handle(self) -> None:
        RAN.append(self.who)


class QuickTimeout(Job):
    """A per-job `retry_after` override (5s, well under the 90s queue-config default)."""

    retry_after = 5

    async def handle(self) -> None:
        RAN.append("quick")


async def _setup() -> tuple[QueueManager, ConnectionResolver]:
    RAN.clear()
    app = Application()
    db = ConnectionResolver()
    app.instance("db", db)
    manager = QueueManager(app, broker=InMemoryBroker(await_inplace=True))
    app.instance("queue", manager)
    set_application(app)
    QueuedJob.set_connection(db)
    await db.execute(sa.schema.CreateTable(QueuedJob.__table__))
    return manager, db


async def test_stuck_reservation_is_reclaimed_after_retry_after_and_rerun() -> None:
    manager, db = await _setup()
    try:
        now = int(time.time())
        await manager.dispatch_after(0, Greet("zombie"))
        row = (await QueuedJob.all())[0]
        # simulate a worker that claimed the row then died before push_instance/delete
        await QueuedJob.where("id", "=", row.id).update({"reserved_at": now - 200})

        released = await manager.release_due_jobs(now=now)
        assert released == 1
        assert RAN == ["zombie"]
        assert await QueuedJob.all() == []
    finally:
        set_application(None)
        await db.dispose()


async def test_a_freshly_reserved_row_is_left_alone() -> None:
    """A row reserved moments ago (still within `retry_after`) is presumed still in flight."""
    manager, db = await _setup()
    try:
        now = int(time.time())
        await manager.dispatch_after(0, Greet("still-running"))
        row = (await QueuedJob.all())[0]
        await QueuedJob.where("id", "=", row.id).update({"reserved_at": now})

        released = await manager.release_due_jobs(now=now)
        assert released == 0
        assert RAN == []
        assert len(await QueuedJob.all()) == 1
    finally:
        set_application(None)
        await db.dispose()


async def test_per_job_retry_after_overrides_the_queue_config_default() -> None:
    manager, db = await _setup()
    try:
        now = int(time.time())
        await manager.dispatch_after(0, QuickTimeout())
        row = (await QueuedJob.all())[0]
        # Simulate a crashed claim: reserved 10s ago with QuickTimeout's 5s override baked into
        # reserved_until at claim time (reserved_at + 5 = now - 5, already past) — so it's overdue
        # under its own override even though the 90s config default hasn't elapsed.
        await QueuedJob.where("id", "=", row.id).update(
            {"reserved_at": now - 10, "reserved_until": now - 5}
        )

        released = await manager.release_due_jobs(now=now)
        assert released == 1
        assert RAN == ["quick"]
    finally:
        set_application(None)
        await db.dispose()
