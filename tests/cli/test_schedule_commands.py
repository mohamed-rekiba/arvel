"""Tests for FR-003/FR-004/FR-005: Schedule CLI commands."""

from __future__ import annotations

from typer.testing import CliRunner

from arvel.cli.app import app
from tests._helpers import strip_ansi

runner = CliRunner()


class TestScheduleGroupRegistered:
    """The 'schedule' command group is accessible."""

    def test_schedule_help(self) -> None:
        result = runner.invoke(app, ["schedule", "--help"])
        assert result.exit_code == 0
        assert "run" in result.output
        assert "work" in result.output
        assert "list" in result.output


class TestScheduleRunCommand:
    """FR-003: schedule run evaluates entries once and exits."""

    def test_schedule_run_help(self) -> None:
        result = runner.invoke(app, ["schedule", "run", "--help"])
        assert result.exit_code == 0

    def test_schedule_run_no_entries(self) -> None:
        """With no schedule file, should succeed with 0 dispatched."""
        result = runner.invoke(app, ["schedule", "run", "--app-dir", "/nonexistent"])
        assert result.exit_code == 0
        assert "0" in result.output or "no" in result.output.lower()


class TestScheduleWorkCommand:
    """FR-004: schedule work runs as daemon."""

    def test_schedule_work_help(self) -> None:
        result = runner.invoke(app, ["schedule", "work", "--help"])
        assert result.exit_code == 0
        assert "--interval" in strip_ansi(result.output)


class TestScheduleListCommand:
    """FR-005: schedule list shows registered entries."""

    def test_schedule_list_help(self) -> None:
        result = runner.invoke(app, ["schedule", "list", "--help"])
        assert result.exit_code == 0
        assert "--json" in strip_ansi(result.output)

    def test_schedule_list_no_entries(self) -> None:
        """With no schedule file, should print empty table."""
        result = runner.invoke(app, ["schedule", "list", "--app-dir", "/nonexistent"])
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "no" in output_lower or "empty" in output_lower or "job" in output_lower

    def test_schedule_list_json_flag(self) -> None:
        """JSON output should produce valid JSON."""
        import json

        result = runner.invoke(app, ["schedule", "list", "--json", "--app-dir", "/nonexistent"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
