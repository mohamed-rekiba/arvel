"""release_due_jobs reserves each row with an atomic compare-and-set, so two concurrent workers
never double-release the same job."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import sqlalchemy as sa

from arvel.database import ConnectionResolver
from arvel.kernel import Application, set_application
from arvel.queue import Job, QueuedJob, QueueManager

RAN: list[str] = []


class _Greet(Job):
    def __init__(self, who: str) -> None:
        self.who = who

    async def handle(self) -> Any:
        RAN.append(self.who)


async def _setup(url: str | None = None) -> tuple[QueueManager, ConnectionResolver]:
    from taskiq import InMemoryBroker

    RAN.clear()
    app = Application()
    # a file-backed url gives each concurrent task its own pooled connection (two real workers);
    # the default in-memory StaticPool shares one connection, which SQLAlchemy can't drive from
    # two tasks at once — fine for the single-threaded tests, not for the concurrent one.
    db = ConnectionResolver({"default": {"url": url}}) if url else ConnectionResolver()
    app.instance("db", db)
    manager = QueueManager(app, broker=InMemoryBroker())
    app.instance("queue", manager)
    set_application(app)
    QueuedJob.set_connection(db)
    await db.execute(sa.schema.CreateTable(QueuedJob.__table__))
    return manager, db


async def test_release_skips_rows_already_reserved_by_another_worker() -> None:
    manager, db = await _setup()
    try:
        now = int(time.time())
        await manager.dispatch_after(0, _Greet("x"))  # due now
        row = (await QueuedJob.all())[0]
        # simulate another worker having claimed it
        await QueuedJob.where("id", "=", row.id).update({"reserved_at": now})
        released = await manager.release_due_jobs(now=now)
        assert released == 0  # reserved → not re-released
        assert RAN == []
        assert len(await QueuedJob.all()) == 1  # left for the owning worker
    finally:
        set_application(None)
        await db.dispose()


async def test_concurrent_release_dispatches_each_job_exactly_once(tmp_path: Any) -> None:
    # a file db so the two concurrent passes are two real pooled connections racing over one row
    # (in-memory sqlite shares a single connection, which two tasks can't safely drive at once)
    db_file = tmp_path / "queue.db"
    manager, db = await _setup(f"sqlite+aiosqlite:///{db_file}")
    try:
        now = int(time.time())
        await manager.dispatch_after(0, _Greet("once"))
        r1, r2 = await asyncio.gather(
            manager.release_due_jobs(now=now), manager.release_due_jobs(now=now)
        )
        assert r1 + r2 == 1  # claimed by exactly one pass
        assert RAN == ["once"]  # ran exactly once
        assert await QueuedJob.all() == []  # released + removed
    finally:
        set_application(None)
        await db.dispose()
