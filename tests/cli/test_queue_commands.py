"""Tests for FR-001/FR-002: Queue CLI commands (queue work, queue restart)."""

from __future__ import annotations

from typer.testing import CliRunner

from arvel.cli.app import app
from tests._helpers import strip_ansi

runner = CliRunner()


class TestQueueGroupRegistered:
    """The 'queue' command group is accessible."""

    def test_queue_help(self) -> None:
        result = runner.invoke(app, ["queue", "--help"])
        assert result.exit_code == 0
        assert "work" in result.output
        assert "restart" in result.output


class TestQueueWorkCommand:
    """FR-001: queue work starts a worker based on driver config."""

    def test_queue_work_help(self) -> None:
        result = runner.invoke(app, ["queue", "work", "--help"])
        assert result.exit_code == 0
        assert "--queue" in strip_ansi(result.output)

    def test_queue_work_sync_driver_warns(self, monkeypatch: object) -> None:
        """Sync driver can't run a real worker — should print a warning."""
        import os

        os.environ["QUEUE_DRIVER"] = "sync"
        result = runner.invoke(app, ["queue", "work"])
        os.environ.pop("QUEUE_DRIVER", None)
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert (
            "sync" in output_lower or "not supported" in output_lower or "warning" in output_lower
        )

    def test_queue_work_null_driver_warns(self) -> None:
        """Null driver can't run a real worker — should print a warning."""
        import os

        os.environ["QUEUE_DRIVER"] = "null"
        result = runner.invoke(app, ["queue", "work"])
        os.environ.pop("QUEUE_DRIVER", None)
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert (
            "null" in output_lower or "not supported" in output_lower or "warning" in output_lower
        )

    def test_queue_work_unknown_driver_fails(self) -> None:
        """Unknown driver should error clearly."""
        import os

        os.environ["QUEUE_DRIVER"] = "nonexistent"
        result = runner.invoke(app, ["queue", "work"])
        os.environ.pop("QUEUE_DRIVER", None)
        assert result.exit_code != 0


class TestQueueRestartCommand:
    """FR-002: queue restart writes a signal file."""

    def test_queue_restart_help(self) -> None:
        result = runner.invoke(app, ["queue", "restart", "--help"])
        assert result.exit_code == 0

    def test_queue_restart_writes_signal(self) -> None:
        from arvel.cli.commands.queue import RESTART_SIGNAL_PATH

        if RESTART_SIGNAL_PATH.exists():
            RESTART_SIGNAL_PATH.unlink()

        result = runner.invoke(app, ["queue", "restart"])
        assert result.exit_code == 0
        assert "restart" in result.output.lower()
        assert RESTART_SIGNAL_PATH.exists()
        assert RESTART_SIGNAL_PATH.read_text() == "restart"

        RESTART_SIGNAL_PATH.unlink(missing_ok=True)
