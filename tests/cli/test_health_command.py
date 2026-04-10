"""Tests for FR-007: Health check CLI command."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from arvel.cli.app import app

runner = CliRunner()


@pytest.mark.integration
@pytest.mark.db
class TestHealthCommand:
    """FR-007: health command checks subsystem connectivity."""

    def test_health_help(self) -> None:
        result = runner.invoke(app, ["health", "--help"])
        assert result.exit_code == 0

    def test_health_runs_checks(self) -> None:
        """Should attempt checks and report results."""
        result = runner.invoke(app, ["health", "check"])
        output_lower = result.output.lower()
        assert "queue" in output_lower or "health" in output_lower or "check" in output_lower

    def test_health_reports_queue_status(self) -> None:
        """Queue check should appear in output."""
        result = runner.invoke(app, ["health", "check"])
        output_lower = result.output.lower()
        assert "queue" in output_lower

    def test_health_reports_database_status(self) -> None:
        """Database check should appear in output."""
        result = runner.invoke(app, ["health", "check"])
        output_lower = result.output.lower()
        assert "database" in output_lower

    def test_health_reports_cache_status(self) -> None:
        """Cache check should appear in output."""
        result = runner.invoke(app, ["health", "check"])
        output_lower = result.output.lower()
        assert "cache" in output_lower
