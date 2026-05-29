"""Tests for ``optimize`` and ``optimize:clear`` commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from arvel.console import Application as ConsoleApplication
from arvel.console.commands.optimize import OptimizeClearCommand, OptimizeCommand
from typer.testing import CliRunner


class TestOptimizeCommand:
    def test_echoes_all_steps(self, tmp_path: Path) -> None:
        cmd = OptimizeCommand()
        app_mock = MagicMock()
        app_mock.base_path = tmp_path
        cmd.app = app_mock

        with (
            patch(
                "arvel.console.commands.optimize.dump_config_cache",
                return_value=2,
            ) as mock_cfg,
            patch(
                "arvel.console.commands.optimize.warm_bytecode_cache",
                return_value=5,
            ) as mock_view,
        ):
            cli = ConsoleApplication([cmd])
            result = CliRunner().invoke(cli.typer_app, ["optimize"])

        assert result.exit_code == 0, result.output
        assert "config:cache" in result.output
        assert "view:cache" in result.output
        assert "route:cache" in result.output
        assert "event:cache" in result.output
        mock_cfg.assert_called_once()
        mock_view.assert_called_once()

    def test_calls_dump_with_correct_path(self, tmp_path: Path) -> None:
        cmd = OptimizeCommand()
        app_mock = MagicMock()
        app_mock.base_path = tmp_path
        cmd.app = app_mock

        captured: list[Path] = []

        def _fake_dump(dest: Path) -> int:
            captured.append(dest)
            return 1

        with (
            patch("arvel.console.commands.optimize.dump_config_cache", side_effect=_fake_dump),
            patch("arvel.console.commands.optimize.warm_bytecode_cache", return_value=0),
        ):
            cli = ConsoleApplication([cmd])
            CliRunner().invoke(cli.typer_app, ["optimize"])

        assert len(captured) == 1
        assert captured[0].name == "config.json"


class TestOptimizeClearCommand:
    def test_clears_view_and_config(self) -> None:
        cmd = OptimizeClearCommand()
        cli = ConsoleApplication([cmd])

        with (
            patch("arvel.console.commands.optimize.clear_bytecode_cache") as mock_bc,
            patch("arvel.console.commands.optimize.reset_cache") as mock_rc,
            patch("arvel.console.commands.optimize.reset") as mock_reset,
        ):
            result = CliRunner().invoke(cli.typer_app, ["optimize:clear"])

        assert result.exit_code == 0, result.output
        assert "view:clear" in result.output
        mock_bc.assert_called_once()
        mock_rc.assert_called_once()
        mock_reset.assert_called_once()

    def test_reports_nothing_when_config_cache_absent(self) -> None:
        cmd = OptimizeClearCommand()
        cli = ConsoleApplication([cmd])

        with (
            patch("arvel.console.commands.optimize.clear_bytecode_cache"),
            patch("arvel.console.commands.optimize.reset_cache"),
            patch("arvel.console.commands.optimize.reset"),
        ):
            result = CliRunner().invoke(cli.typer_app, ["optimize:clear"])

        assert result.exit_code == 0, result.output
        assert "nothing to clear" in result.output.lower()

    def test_removes_existing_config_cache(self, tmp_path: Path) -> None:
        cache = tmp_path / "config.json"
        cache.write_text("{}")

        cmd = OptimizeClearCommand()
        cli = ConsoleApplication([cmd])

        with (
            patch("arvel.console.commands.optimize.clear_bytecode_cache"),
            patch("arvel.console.commands.optimize.reset_cache"),
            patch("arvel.console.commands.optimize.reset"),
            patch("arvel.console.commands.optimize._CONFIG_CACHE_REL", cache),
        ):
            result = CliRunner().invoke(cli.typer_app, ["optimize:clear"])

        assert result.exit_code == 0, result.output
        assert not cache.exists()
        assert "removed" in result.output.lower()
