"""Unit tests for queue console commands — FR-008-018..022, updated for WI-021.

These exercise the private async work methods (``_run`` / ``_list`` / ``_retry`` /
``_flush`` / ``_forget``) directly. The Typer-callback path is covered separately
by ``tests/test_queue/commands/test_typer_registration.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from arvel.queue.config import QueueDriver


class TestQueueWorkCommand:
    """FR-008-018: queue:work starts the worker loop."""

    def test_command_name(self) -> None:
        from arvel.queue.commands.queue_work import QueueWorkCommand

        assert QueueWorkCommand.name == "queue:work"

    @pytest.mark.asyncio
    async def test_drain_then_stop_invokes_worker(self) -> None:
        from arvel.queue.commands.queue_work import QueueWorkCommand
        from arvel.queue.config import QueueConfig
        from arvel.queue.manager import QueueManager
        from arvel.queue.worker import Worker

        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        cmd = QueueWorkCommand(manager)

        with patch.object(Worker, "drain_then_stop", new_callable=AsyncMock) as mock_drain:
            await cmd.run_worker(queue="default", stop_when_empty=True)
            mock_drain.assert_awaited_once()


class TestQueueFailedCommand:
    """FR-008-019: queue:failed lists failed jobs."""

    def test_command_name(self) -> None:
        from arvel.queue.commands.queue_failed import QueueFailedCommand

        assert QueueFailedCommand.name == "queue:failed"

    @pytest.mark.asyncio
    async def test_list_calls_list_all(self) -> None:
        from arvel.queue.commands.queue_failed import QueueFailedCommand
        from arvel.queue.failed_job_store import FailedJobStore

        store = AsyncMock(spec=FailedJobStore)
        store.list_all.return_value = []
        cmd = QueueFailedCommand(store)
        await cmd.list_failed(None)
        store.list_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_failed_prints_rows_when_non_empty(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from datetime import UTC, datetime
        from unittest.mock import MagicMock

        from arvel.queue.commands.queue_failed import QueueFailedCommand
        from arvel.queue.failed_job_store import FailedJobStore

        row = MagicMock()
        row.uuid = "abc-123"
        row.queue = "default"
        row.failed_at = datetime(2026, 5, 19, tzinfo=UTC)

        store = AsyncMock(spec=FailedJobStore)
        store.list_all.return_value = [row]
        cmd = QueueFailedCommand(store)
        await cmd.list_failed(None)

        out = capsys.readouterr().out
        assert "abc-123" in out
        assert "default" in out

    @pytest.mark.asyncio
    async def test_list_failed_filters_by_queue(self, capsys: pytest.CaptureFixture[str]) -> None:
        from datetime import UTC, datetime
        from unittest.mock import MagicMock

        from arvel.queue.commands.queue_failed import QueueFailedCommand
        from arvel.queue.failed_job_store import FailedJobStore

        row_keep = MagicMock(
            uuid="kept", queue="emails", failed_at=datetime(2026, 5, 19, tzinfo=UTC)
        )
        row_drop = MagicMock(
            uuid="dropped", queue="default", failed_at=datetime(2026, 5, 19, tzinfo=UTC)
        )

        store = AsyncMock(spec=FailedJobStore)
        store.list_all.return_value = [row_keep, row_drop]
        cmd = QueueFailedCommand(store)
        await cmd.list_failed("emails")

        out = capsys.readouterr().out
        assert "kept" in out
        assert "dropped" not in out


class TestQueueRetryCommand:
    """FR-008-020: queue:retry re-dispatches a failed job."""

    def test_command_name(self) -> None:
        from arvel.queue.commands.queue_retry import QueueRetryCommand

        assert QueueRetryCommand.name == "queue:retry"

    @pytest.mark.asyncio
    async def test_retry_dispatches_found_job(self) -> None:
        from arvel.queue.commands.queue_retry import QueueRetryCommand
        from arvel.queue.config import QueueConfig, QueueDriver
        from arvel.queue.drivers.database import DatabaseConnection
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
        failed = FailedJob(
            uuid="test-uuid",
            queue="default",
            payload=env.to_json(),
            error="err",
        )

        store = AsyncMock(spec=FailedJobStore)
        store.find.return_value = failed
        store.delete = AsyncMock(return_value=True)

        db_conn = DatabaseConnection()
        await db_conn.setup()
        manager = QueueManager(QueueConfig(connection=QueueDriver.DATABASE))
        manager._connections[QueueDriver.DATABASE] = db_conn  # pyright: ignore[reportPrivateUsage]

        cmd = QueueRetryCommand(manager, store)
        await cmd.retry("test-uuid")

        store.find.assert_awaited_once_with("test-uuid")

    @pytest.mark.asyncio
    async def test_retry_not_found_raises(self) -> None:
        from arvel.queue.commands.queue_retry import QueueRetryCommand
        from arvel.queue.config import QueueConfig, QueueDriver
        from arvel.queue.drivers.database import DatabaseConnection
        from arvel.queue.failed_job_store import FailedJobStore
        from arvel.queue.manager import QueueManager

        store = AsyncMock(spec=FailedJobStore)
        store.find.return_value = None

        db_conn = DatabaseConnection()
        await db_conn.setup()
        manager = QueueManager(QueueConfig(connection=QueueDriver.DATABASE))
        manager._connections[QueueDriver.DATABASE] = db_conn  # pyright: ignore[reportPrivateUsage]

        cmd = QueueRetryCommand(manager, store)
        with pytest.raises(ValueError, match="not found"):
            await cmd.retry("no-such-uuid")


class TestQueueFlushCommand:
    """FR-008-021: queue:flush clears all failed jobs."""

    def test_command_name(self) -> None:
        from arvel.queue.commands.queue_flush import QueueFlushCommand

        assert QueueFlushCommand.name == "queue:flush"

    @pytest.mark.asyncio
    async def test_flush_calls_store_flush(self) -> None:
        from arvel.queue.commands.queue_flush import QueueFlushCommand
        from arvel.queue.failed_job_store import FailedJobStore

        store = AsyncMock(spec=FailedJobStore)
        cmd = QueueFlushCommand(store)
        await cmd.flush()
        store.flush.assert_awaited_once()


class TestQueueForgetCommand:
    """FR-008-022: queue:forget deletes one failed job by UUID."""

    def test_command_name(self) -> None:
        from arvel.queue.commands.queue_forget import QueueForgetCommand

        assert QueueForgetCommand.name == "queue:forget"

    @pytest.mark.asyncio
    async def test_forget_calls_delete(self) -> None:
        from arvel.queue.commands.queue_forget import QueueForgetCommand
        from arvel.queue.failed_job_store import FailedJobStore

        store = AsyncMock(spec=FailedJobStore)
        store.delete.return_value = True
        cmd = QueueForgetCommand(store)
        await cmd.forget("some-uuid")
        store.delete.assert_awaited_once_with("some-uuid")

    @pytest.mark.asyncio
    async def test_forget_not_found_raises(self) -> None:
        from arvel.queue.commands.queue_forget import QueueForgetCommand
        from arvel.queue.failed_job_store import FailedJobStore

        store = AsyncMock(spec=FailedJobStore)
        store.delete.return_value = False
        cmd = QueueForgetCommand(store)
        with pytest.raises(ValueError, match="not found"):
            await cmd.forget("ghost-uuid")
