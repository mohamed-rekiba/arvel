"""Delayed dispatch (Laravel ``dispatch()->delay()``) — durable, DB-backed via the ``jobs`` table.
``dispatch_after(seconds, job)`` persists a row with ``available_at`` in the future instead of
enqueuing immediately; a worker/scheduler calls ``release_due_jobs()`` to push the due ones onto the
broker and delete their rows. Durable across restarts (rows persist); needs a configured database."""

from __future__ import annotations

import asyncio
import contextlib
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


async def _setup() -> tuple[QueueManager, ConnectionResolver]:
    from taskiq import InMemoryBroker

    RAN.clear()
    app = Application()
    db = ConnectionResolver()
    app.instance("db", db)
    manager = QueueManager(app, broker=InMemoryBroker())
    app.instance("queue", manager)
    set_application(app)
    QueuedJob.set_connection(db)
    await db.execute(sa.schema.CreateTable(QueuedJob.__table__))
    return manager, db


async def test_dispatch_after_persists_a_future_row_not_an_immediate_enqueue() -> None:
    manager, db = await _setup()
    try:
        await manager.dispatch_after(3600, _Greet("ada"))
        rows = await QueuedJob.all()
        assert len(rows) == 1
        assert rows[0].available_at > int(time.time())  # scheduled in the future
        assert "_Greet" in rows[0].payload
        assert RAN == []  # not run yet — it's delayed
    finally:
        set_application(None)
        await db.dispose()


async def test_release_due_jobs_runs_only_due_rows_and_removes_them() -> None:
    manager, db = await _setup()
    try:
        now = int(time.time())
        await manager.dispatch_after(0, _Greet("now"))  # available_at == now → due
        await manager.dispatch_after(3600, _Greet("later"))  # due in an hour
        released = await manager.release_due_jobs(now=now)
        assert released == 1  # only the due one
        assert RAN == ["now"]  # it actually ran through the broker
        remaining = await QueuedJob.all()
        assert len(remaining) == 1 and "later" in remaining[0].payload  # the future one stays
    finally:
        set_application(None)
        await db.dispose()


async def test_delayed_job_fires_through_a_running_worker() -> None:
    # the PRODUCTION path: work() must release due jobs via its release loop (not a direct call).
    # If work()'s receiver.listen() wiring is broken, the worker crashes and the job never runs.
    manager, db = await _setup()
    try:
        await manager.dispatch_after(0, _Greet("worker"))  # due now, sitting in the jobs table
        worker = asyncio.create_task(manager.work(release_interval=0.05))
        try:
            for _ in range(40):  # up to ~2s for the release loop to fire it
                await asyncio.sleep(0.05)
                if RAN:
                    break
        finally:
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker
        assert RAN == ["worker"]  # ran via work()'s release loop
        assert await QueuedJob.all() == []  # released + deleted
    finally:
        set_application(None)
        await db.dispose()


async def test_dispatch_after_without_a_database_raises_clearly() -> None:
    set_application(None)
    from taskiq import InMemoryBroker

    manager = QueueManager(broker=InMemoryBroker())
    try:
        import pytest

        with pytest.raises(RuntimeError, match="database"):
            await manager.dispatch_after(60, _Greet("x"))
    finally:
        set_application(None)
