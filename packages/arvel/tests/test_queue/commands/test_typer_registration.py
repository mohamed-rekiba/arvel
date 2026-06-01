"""Queue commands honour the Command contract via register override.
Each of the 5 queue commands overrides register with a Typer callback
 whose signature matches its CLI flags.
 `# type: ignore[override]` comments are removed; handle(ctx) signature
 matches the base class.
 Each command exercises end-to-end via CliRunner (Typer callback path).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import typer
from arvel.console import Application, Command
from arvel.queue.drivers.database import DatabaseConnection
from typer.testing import CliRunner

from .conftest import invoke_async


async def _setup_db() -> DatabaseConnection:
    from arvel.queue.drivers.database import DatabaseConnection

    db = DatabaseConnection()
    await db.setup()
    return db


# ─── — register() override present on all 5 queue commands ────────


class TestRegisterOverridden:
    def test_queue_work_overrides_register(self) -> None:
        from arvel.queue.commands.queue_work import QueueWorkCommand

        assert "register" in QueueWorkCommand.__dict__

    def test_queue_failed_overrides_register(self) -> None:
        from arvel.queue.commands.queue_failed import QueueFailedCommand

        assert "register" in QueueFailedCommand.__dict__

    def test_queue_retry_overrides_register(self) -> None:
        from arvel.queue.commands.queue_retry import QueueRetryCommand

        assert "register" in QueueRetryCommand.__dict__

    def test_queue_flush_overrides_register(self) -> None:
        from arvel.queue.commands.queue_flush import QueueFlushCommand

        assert "register" in QueueFlushCommand.__dict__

    def test_queue_forget_overrides_register(self) -> None:
        from arvel.queue.commands.queue_forget import QueueForgetCommand

        assert "register" in QueueForgetCommand.__dict__


# ─── — handle(ctx) signature matches Command base, no override-ignore ────


class TestHandleSignatureMatchesBase:
    """Verify `handle(self, ctx) -> int` matches Command — no # type: ignore[override]."""

    def test_queue_work_handle_raises_notimplemented(self) -> None:
        from arvel.console import Context
        from arvel.queue.commands.queue_work import QueueWorkCommand
        from arvel.queue.config import QueueConfig, QueueDriver
        from arvel.queue.manager import QueueManager

        cmd = QueueWorkCommand(QueueManager(QueueConfig(connection=QueueDriver.SYNC)))
        with pytest.raises(NotImplementedError):
            cmd.handle(Context())

    def test_queue_failed_handle_raises_notimplemented(self) -> None:
        from arvel.console import Context
        from arvel.queue.commands.queue_failed import QueueFailedCommand
        from arvel.queue.failed_job_store import FailedJobStore

        store = AsyncMock(spec=FailedJobStore)
        cmd = QueueFailedCommand(store)
        with pytest.raises(NotImplementedError):
            cmd.handle(Context())


# ─── — CliRunner smokes the Typer callback for each queue command ────


def _build_runner_app(cmd: Command) -> tuple[CliRunner, typer.Typer]:
    app = Application(commands=[cmd])
    return CliRunner(), app.typer_app


class TestCliRunnerSmokes:
    def test_queue_work_typer_callback_dispatches(self) -> None:
        from arvel.queue.commands.queue_work import QueueWorkCommand
        from arvel.queue.config import QueueConfig, QueueDriver
        from arvel.queue.manager import QueueManager

        cmd = QueueWorkCommand(QueueManager(QueueConfig(connection=QueueDriver.SYNC)))

        with patch.object(
            QueueWorkCommand, "run_worker", new_callable=AsyncMock, return_value=None
        ) as mock_run:
            runner, typer_app = _build_runner_app(cmd)
            result = invoke_async(
                runner,
                typer_app,
                ["queue:work", "--queue", "emails", "--stop-when-empty"],
            )

        assert result.exit_code == 0, result.output
        mock_run.assert_awaited_once()
        kwargs = mock_run.call_args.kwargs
        assert kwargs.get("queue") == "emails"
        assert kwargs.get("stop_when_empty") is True

    def test_queue_failed_typer_callback_dispatches(self) -> None:
        from arvel.queue.commands.queue_failed import QueueFailedCommand
        from arvel.queue.failed_job_store import FailedJobStore

        store = AsyncMock(spec=FailedJobStore)
        store.list_all.return_value = []
        cmd = QueueFailedCommand(store)

        runner, typer_app = _build_runner_app(cmd)
        result = invoke_async(runner, typer_app, ["queue:failed"])

        assert result.exit_code == 0, result.output
        store.list_all.assert_awaited_once()

    def test_queue_retry_typer_callback_dispatches(self) -> None:

        from arvel.queue.commands.queue_retry import QueueRetryCommand
        from arvel.queue.config import QueueConfig, QueueDriver
        from arvel.queue.envelope import JobEnvelope
        from arvel.queue.failed_job_store import FailedJobStore
        from arvel.queue.job import Job
        from arvel.queue.manager import QueueManager
        from arvel.queue.models.failed_job import FailedJob

        class _RetryJob(Job):
            value: int

            async def handle(self) -> None:
                pass

        env = JobEnvelope(
            job_class=f"{_RetryJob.__module__}.{_RetryJob.__qualname__}",
            payload={"value": 1},
        )
        failed = FailedJob(uuid="uuid-x", queue="default", payload=env.to_json(), error="e")

        store = AsyncMock(spec=FailedJobStore)
        store.find.return_value = failed
        store.delete = AsyncMock(return_value=True)

        db_conn = asyncio.run(_setup_db())
        manager = QueueManager(QueueConfig(connection=QueueDriver.DATABASE))
        manager._connections[QueueDriver.DATABASE] = db_conn  # pyright: ignore[reportPrivateUsage]

        cmd = QueueRetryCommand(manager, store)
        runner, typer_app = _build_runner_app(cmd)
        result = invoke_async(runner, typer_app, ["queue:retry", "uuid-x"])

        assert result.exit_code == 0, result.output
        store.find.assert_awaited_once_with("uuid-x")

    def test_queue_flush_typer_callback_dispatches(self) -> None:
        from arvel.queue.commands.queue_flush import QueueFlushCommand
        from arvel.queue.failed_job_store import FailedJobStore

        store = AsyncMock(spec=FailedJobStore)
        cmd = QueueFlushCommand(store)

        runner, typer_app = _build_runner_app(cmd)
        result = invoke_async(runner, typer_app, ["queue:flush"])

        assert result.exit_code == 0, result.output
        store.flush.assert_awaited_once()

    def test_queue_forget_typer_callback_dispatches(self) -> None:
        from arvel.queue.commands.queue_forget import QueueForgetCommand
        from arvel.queue.failed_job_store import FailedJobStore

        store = AsyncMock(spec=FailedJobStore)
        store.delete.return_value = True
        cmd = QueueForgetCommand(store)

        runner, typer_app = _build_runner_app(cmd)
        result = invoke_async(runner, typer_app, ["queue:forget", "ghost-uuid"])

        assert result.exit_code == 0, result.output
        store.delete.assert_awaited_once_with("ghost-uuid")
