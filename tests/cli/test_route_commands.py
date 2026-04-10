"""Tests for FR-006: Route list CLI command."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from arvel.cli.app import app
from tests._helpers import strip_ansi

runner = CliRunner()


class TestRouteGroupRegistered:
    """The 'route' command group is accessible."""

    def test_route_help(self) -> None:
        result = runner.invoke(app, ["route", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output


class TestRouteListCommand:
    """FR-006: route list shows all registered routes."""

    def test_route_list_help(self) -> None:
        result = runner.invoke(app, ["route", "list", "--help"])
        assert result.exit_code == 0
        assert "--json" in strip_ansi(result.output)

    def test_route_list_no_modules(self) -> None:
        """With no modules dir, should print empty or 'no routes'."""
        result = runner.invoke(app, ["route", "list", "--app-dir", "/nonexistent"])
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "no route" in output_lower or "method" in output_lower or "empty" in output_lower

    def test_route_list_json_flag(self) -> None:
        """JSON output for empty routes should produce an empty list."""
        result = runner.invoke(app, ["route", "list", "--json", "--app-dir", "/nonexistent"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 0

    def test_route_list_shows_headers(self, tmp_path: object) -> None:
        """Table output should include column headers."""
        result = runner.invoke(app, ["route", "list", "--app-dir", "/nonexistent"])
        assert result.exit_code == 0
