"""Tests for view:cache / view:clear commands and warm_bytecode_cache."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


class TestWarmBytecodeCache:
    """warm_bytecode_cache creates bootstrap/views/ and returns template count."""

    def test_returns_zero_for_empty_template_dir(self, tmp_path: Path) -> None:
        from arvel.support.view import warm_bytecode_cache

        template_dir = tmp_path / "views"
        template_dir.mkdir()

        with (
            patch("arvel.support.view._BYTECODE_CACHE_DIR", tmp_path / "bootstrap" / "views"),
            patch("arvel.support.view._resolve_paths", return_value=[str(template_dir)]),
            patch("arvel.support.view._environment_cache", None),
        ):
            count = warm_bytecode_cache()

        assert count == 0
        assert (tmp_path / "bootstrap" / "views").is_dir()

    def test_compiles_templates(self, tmp_path: Path) -> None:
        from arvel.support.view import warm_bytecode_cache

        template_dir = tmp_path / "views"
        template_dir.mkdir()
        (template_dir / "hello.html").write_text("<p>{{ name }}</p>")
        (template_dir / "bye.txt").write_text("bye {{ name }}")

        cache_dir = tmp_path / "bootstrap" / "views"

        with (
            patch("arvel.support.view._BYTECODE_CACHE_DIR", cache_dir),
            patch("arvel.support.view._resolve_paths", return_value=[str(template_dir)]),
            patch("arvel.support.view._environment_cache", None),
        ):
            count = warm_bytecode_cache()

        assert count == 2
        assert cache_dir.is_dir()


class TestClearBytecodeCache:
    """clear_bytecode_cache removes .cache files from bootstrap/views/."""

    def test_no_error_when_cache_dir_missing(self) -> None:
        from arvel.support.view import clear_bytecode_cache

        with patch("arvel.support.view._BYTECODE_CACHE_DIR", Path("/nonexistent/__views__")):
            clear_bytecode_cache()  # must not raise

    def test_deletes_cache_files(self, tmp_path: Path) -> None:
        from arvel.support.view import clear_bytecode_cache

        cache_dir = tmp_path / "bootstrap" / "views"
        cache_dir.mkdir(parents=True)
        (cache_dir / "abc.cache").write_text("x")
        (cache_dir / "def.cache").write_text("y")

        with patch("arvel.support.view._BYTECODE_CACHE_DIR", cache_dir):
            clear_bytecode_cache()

        assert list(cache_dir.iterdir()) == []


class TestViewCacheCommand:
    """view:cache command calls warm_bytecode_cache and echoes the count."""

    def test_command_echoes_template_count(self) -> None:
        from arvel.console import Application
        from arvel.console.commands.view_commands import ViewCacheCommand
        from typer.testing import CliRunner

        cmd = ViewCacheCommand()
        app = Application([cmd])

        # Patch the name as imported in view_commands module
        with patch("arvel.console.commands.view_commands.warm_bytecode_cache", return_value=3):
            result = CliRunner().invoke(app.typer_app, ["view:cache"])

        assert result.exit_code == 0
        assert "3" in result.output


class TestViewClearCommandWithBytecodeCache:
    """view:clear now also removes bytecode cache files."""

    def test_clear_resets_env_and_bytecode(self) -> None:
        from arvel.console import Application
        from arvel.console.commands.view_commands import ViewClearCommand
        from typer.testing import CliRunner

        cmd = ViewClearCommand()
        app = Application([cmd])

        with (
            patch("arvel.console.commands.view_commands.clear_bytecode_cache") as mock_clear_bc,
            patch("arvel.console.commands.view_commands.reset_cache") as mock_reset,
        ):
            result = CliRunner().invoke(app.typer_app, ["view:clear"])

        assert result.exit_code == 0
        mock_clear_bc.assert_called_once()
        mock_reset.assert_called_once()
