"""Failed-job persistence (doc 12) — Laravel parity. When a job exhausts its retries the worker
records a row in the ``failed_jobs`` table (serialized payload + exception); ``FailedJob.retry()``
re-dispatches it and removes the record. Without a bound DB the worker degrades gracefully — the
job's ``failed()`` hook still runs, nothing is persisted, nothing crashes."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from arvel.database import ConnectionResolver
from arvel.kernel import Application, set_application
from arvel.queue import FailedJob, Job, QueueManager, run_job_with_retries


async def _noop(_seconds: Any) -> None:
    return None


RAN: list[str] = []


class _Boom(Job):
    tries = 1

    async def handle(self) -> Any:
        raise RuntimeError("boom")


class _Ok(Job):
    tries = 1

    def __init__(self, tag: str = "ok") -> None:
        self.tag = tag

    async def handle(self) -> Any:
        RAN.append(self.tag)


async def _setup() -> tuple[Application, ConnectionResolver]:
    app = Application()
    db = ConnectionResolver()
    app.instance("db", db)
    set_application(app)
    FailedJob.set_connection(db)
    await db.execute(sa.schema.CreateTable(FailedJob.__table__))
    return app, db


async def test_exhausted_job_is_recorded() -> None:
    _app, db = await _setup()
    try:
        await run_job_with_retries(_Boom(), sleep=_noop)
        rows = await FailedJob.all()
        assert len(rows) == 1
        assert rows[0].queue == "default"
        assert "boom" in rows[0].exception
        assert "_Boom" in rows[0].payload  # serialized job, so it can be retried
    finally:
        set_application(None)
        await db.dispose()


async def test_no_db_does_not_crash() -> None:
    set_application(None)  # no app / no DB bound
    await run_job_with_retries(_Boom(), sleep=_noop)  # graceful: failed() hook runs, no persistence


async def test_retry_redispatches_and_removes_the_record() -> None:
    app, db = await _setup()
    try:
        from taskiq import InMemoryBroker

        from arvel.queue import serialize_instance

        RAN.clear()
        app.instance("queue", QueueManager(app, broker=InMemoryBroker()))
        # a recorded failure whose underlying job now succeeds on re-dispatch
        await FailedJob.create(
            queue="default",
            payload=serialize_instance(_Ok("retried")),
            exception="RuntimeError: boom",
            failed_at=None,
        )
        failed = (await FailedJob.all())[0]
        await failed.retry()
        assert RAN == ["retried"]  # the job actually re-ran through the broker
        assert (
            await FailedJob.all() == []
        )  # and the record was removed (it succeeded, no re-record)
    finally:
        set_application(None)
        await db.dispose()
