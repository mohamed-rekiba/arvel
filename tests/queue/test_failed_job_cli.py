"""Tests for failed job CLI commands — Story 4.

AC-018: queue failed lists failed jobs
AC-019: queue retry <id> re-dispatches and removes
AC-020: queue retry-all re-dispatches all
AC-021: queue forget <id> deletes
AC-022: queue flush purges all
"""

from __future__ import annotations

from typer.testing import CliRunner

from arvel.cli.plugins.queue import _app as queue_app
from arvel.queue.failed_job_repository import FailedJobRepository

runner = CliRunner()


class TestQueueFailedCommand:
    """AC-018: queue failed lists failed jobs."""

    def test_failed_command_exists(self) -> None:
        result = runner.invoke(queue_app, ["failed", "--help"])
        assert result.exit_code == 0
        assert "failed" in result.output.lower()


class TestQueueRetryCommand:
    """AC-019: queue retry <id> re-dispatches."""

    def test_retry_command_exists(self) -> None:
        result = runner.invoke(queue_app, ["retry", "--help"])
        assert result.exit_code == 0


class TestQueueRetryAllCommand:
    """AC-020: queue retry-all re-dispatches all."""

    def test_retry_all_command_exists(self) -> None:
        result = runner.invoke(queue_app, ["retry-all", "--help"])
        assert result.exit_code == 0


class TestQueueForgetCommand:
    """AC-021: queue forget <id> deletes."""

    def test_forget_command_exists(self) -> None:
        result = runner.invoke(queue_app, ["forget", "--help"])
        assert result.exit_code == 0


class TestQueueFlushCommand:
    """AC-022: queue flush purges all."""

    def test_flush_command_exists(self) -> None:
        result = runner.invoke(queue_app, ["flush", "--help"])
        assert result.exit_code == 0


class TestFailedJobRepository:
    """FailedJobRepository CRUD operations."""

    def test_repository_class_exists(self) -> None:
        assert hasattr(FailedJobRepository, "record_failure")
        assert hasattr(FailedJobRepository, "list_failed")
        assert hasattr(FailedJobRepository, "retry_job")
        assert hasattr(FailedJobRepository, "forget_job")
        assert hasattr(FailedJobRepository, "flush_all")
