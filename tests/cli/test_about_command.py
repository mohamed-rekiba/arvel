"""Tests for arvel about command."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from arvel.cli.app import app

runner = CliRunner()


class TestAboutCommand:
    def test_about_help(self) -> None:
        result = runner.invoke(app, ["about", "--help"])
        assert result.exit_code == 0
        assert "framework" in result.output.lower()

    def test_about_default(self) -> None:
        result = runner.invoke(app, ["about"])
        assert result.exit_code == 0
        assert "Arvel Framework" in result.output
        assert "Version:" in result.output
        assert "Python:" in result.output
        assert "Platform:" in result.output

    def test_about_json(self) -> None:
        result = runner.invoke(app, ["about", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["framework"] == "Arvel"
        assert "version" in data
        assert "python" in data
