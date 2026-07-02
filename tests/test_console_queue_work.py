"""Console (doc 13) — queue:work resolves + runs the bound queue manager's worker."""

from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

from arvel.console import build_cli

runner = CliRunner()


class _RetryMe:
    """A trivially serializable job for the queue:retry round-trip."""

    queue = "default"

    async def handle(self) -> None:  # pragma: no cover - never executed in the CLI test
        return None


def test_queue_work_invokes_manager_work() -> None:
    from arvel.kernel import Application, set_application

    class FakeManager:
        def __init__(self) -> None:
            self.queues: Any = None

        async def work(self, queues: Any = None) -> None:
            self.queues = queues

    fake = FakeManager()
    app = Application()
    app.instance("queue", fake)
    set_application(app)
    try:
        result = runner.invoke(build_cli(), ["queue:work", "--queue", "default,mail"])
        assert result.exit_code == 0, result.output
        assert fake.queues == ["default", "mail"]
    finally:
        set_application(None)


def test_queue_failed_lists_and_retry_redispatches(tmp_path: Any) -> None:
    """queue:failed lists the failed_jobs rows; queue:retry re-dispatches one and deletes it
    (Laravel parity). Seeded via a file-backed sqlite so the CLI's own event loop sees it."""
    import asyncio

    import sqlalchemy as sa

    from arvel.database import ConnectionResolver
    from arvel.dates import Date
    from arvel.kernel import Application, set_application
    from arvel.queue import FailedJob, serialize_instance

    url = f"sqlite+aiosqlite:///{tmp_path / 'failed.sqlite'}"

    async def seed() -> str:
        db = ConnectionResolver({"default": {"url": url}})
        FailedJob.set_connection(db)
        await db.execute(sa.schema.CreateTable(FailedJob.__table__))
        row = await FailedJob.create(
            queue="default",
            payload=serialize_instance(_RetryMe()),
            exception="RuntimeError: boom",
            failed_at=Date.now(),
        )
        await db.dispose()
        return str(row.id)

    failed_id = asyncio.run(seed())

    class FakeManager:
        def __init__(self) -> None:
            self.pushed: list[Any] = []

        async def push_instance(self, job: Any) -> None:
            self.pushed.append(job)

    fake = FakeManager()
    app = Application()
    app.instance("queue", fake)
    set_application(app)
    FailedJob.set_connection(ConnectionResolver({"default": {"url": url}}))
    try:
        listed = runner.invoke(build_cli(), ["queue:failed"])
        assert listed.exit_code == 0, listed.output
        assert failed_id in listed.output
        assert "RuntimeError: boom" in listed.output

        retried = runner.invoke(build_cli(), ["queue:retry", failed_id])
        assert retried.exit_code == 0, retried.output
        assert len(fake.pushed) == 1  # re-dispatched onto the queue

        # the record is deleted → nothing left to list or retry
        assert "no failed jobs" in runner.invoke(build_cli(), ["queue:failed"]).output
        assert runner.invoke(build_cli(), ["queue:retry", failed_id]).exit_code == 1
    finally:
        FailedJob.set_connection(None)
        set_application(None)


def test_queue_work_without_queue_errors() -> None:
    from arvel.kernel import Application, set_application

    set_application(Application())  # active app, but no 'queue' bound → binding-missing branch
    try:
        result = runner.invoke(build_cli(), ["queue:work"])
        assert result.exit_code == 1
        assert "no queue bound" in result.output
    finally:
        set_application(None)
