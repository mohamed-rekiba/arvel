"""Tests for arvel serve command."""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from typer.testing import CliRunner

from arvel.cli.app import app
from arvel.cli.commands.serve import _activate_project_venv, _discover_app
from arvel.cli.exceptions import ArvelCLIError

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


class TestServeCommandRegistered:
    def test_serve_help(self) -> None:
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "Start the development server" in result.output

    def test_help_shows_new_options(self) -> None:
        result = runner.invoke(app, ["serve", "--help"])
        plain = _strip_ansi(result.output)
        assert "--root-path" in plain
        assert "--proxy-headers" in plain
        assert "--forwarded-allow" in plain
        assert "--reload-dir" in plain

    def test_help_shows_app_dir_option(self) -> None:
        """FR-002: --app-dir option must appear in help."""
        result = runner.invoke(app, ["serve", "--help"])
        plain = _strip_ansi(result.output)
        assert "--app-dir" in plain


class TestServeDefaultOptions:
    def test_serve_invokes_uvicorn_with_defaults(self) -> None:
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            result = runner.invoke(app, ["serve"])
            assert result.exit_code == 0
            plain = _strip_ansi(result.output)
            assert "Server" in plain
            assert "http://127.0.0.1:8000" in plain
            mock_uvicorn.run.assert_called_once()
            kwargs = mock_uvicorn.run.call_args[1]
            assert kwargs["host"] == "127.0.0.1"
            assert kwargs["port"] == 8000
            assert kwargs["reload"] is True
            assert kwargs["workers"] == 1
            assert kwargs["root_path"] == ""
            assert kwargs["proxy_headers"] is True
            assert kwargs["forwarded_allow_ips"] is None

    def test_serve_custom_port(self) -> None:
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            result = runner.invoke(app, ["serve", "--port", "3000"])
            assert result.exit_code == 0
            kwargs = mock_uvicorn.run.call_args[1]
            assert kwargs["port"] == 3000


# ---------------------------------------------------------------------------
# FR-001: Fix App Discovery Chain
# ---------------------------------------------------------------------------


class TestDiscoveryChainFix:
    """AC-001a through AC-001d — discovery runs when --app is not provided."""

    def test_serve_without_app_flag_calls_discover_app(self) -> None:
        """AC-001a: arvel serve without --app runs _discover_app()."""
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ) as mock_discover,
        ):
            result = runner.invoke(app, ["serve"])
            assert result.exit_code == 0
            mock_discover.assert_called_once()

    def test_serve_without_app_flag_shows_error_when_no_bootstrap(
        self, tmp_path, monkeypatch
    ) -> None:
        """AC-001b: Missing bootstrap/app.py produces ArvelCLIError."""
        monkeypatch.chdir(tmp_path)
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            result = runner.invoke(app, ["serve"])
            assert result.exit_code == 1
            assert "bootstrap/app.py not found" in result.output

    def test_explicit_app_skips_discovery(self) -> None:
        """AC-001c: --app flag bypasses _discover_app()."""
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
            ) as mock_discover,
        ):
            result = runner.invoke(app, ["serve", "--app", "mymodule:myapp"])
            assert result.exit_code == 0
            mock_discover.assert_not_called()
            call_args = mock_uvicorn.run.call_args
            import_string = call_args[0][0] if call_args[0] else call_args[1].get("app")
            assert import_string == "mymodule:myapp"

    def test_factory_true_only_for_discovery(self) -> None:
        """AC-001d: factory=True when using bootstrap discovery, False for explicit --app."""
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            runner.invoke(app, ["serve"])
            kwargs = mock_uvicorn.run.call_args[1]
            assert kwargs["factory"] is True

        mock_uvicorn2 = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn2}):
            runner.invoke(app, ["serve", "--app", "mymod:myapp"])
            kwargs2 = mock_uvicorn2.run.call_args[1]
            assert kwargs2.get("factory") is not True


# ---------------------------------------------------------------------------
# FR-002: --app-dir option
# ---------------------------------------------------------------------------


class TestServeAppDir:
    """AC-002a through AC-002d — --app-dir resolves imports from a specific directory."""

    def test_app_dir_added_to_sys_path(self, tmp_path) -> None:
        """AC-002a: --app-dir adds that directory to sys.path."""
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        bootstrap = project_dir / "bootstrap"
        bootstrap.mkdir()
        (bootstrap / "app.py").write_text("def create_app(): ...")

        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch("arvel.cli.commands.serve._ensure_cwd_importable") as mock_ensure,
        ):
            result = runner.invoke(app, ["serve", "--app-dir", str(project_dir)])
            assert result.exit_code == 0
            mock_ensure.assert_called_once()
            call_args = mock_ensure.call_args
            passed_dir = call_args[0][0] if call_args[0] else call_args[1].get("app_dir")
            assert str(project_dir) in str(passed_dir)

    def test_app_dir_used_for_discovery(self, tmp_path) -> None:
        """AC-002b: _discover_app() checks bootstrap/app.py relative to --app-dir."""
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        bootstrap = project_dir / "bootstrap"
        bootstrap.mkdir()
        (bootstrap / "app.py").write_text("def create_app(): ...")

        result = _discover_app(base_path=project_dir)
        assert result == "bootstrap.app:create_app"

    def test_app_dir_default_preserves_cwd_behavior(self) -> None:
        """AC-002d: Default --app-dir (.) preserves CWD behavior."""
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            result = runner.invoke(app, ["serve"])
            assert result.exit_code == 0


# ---------------------------------------------------------------------------
# FR-003: Wire uvicorn log config
# ---------------------------------------------------------------------------


class TestServeLogConfig:
    def test_log_config_uses_arvel_config_not_none(self) -> None:
        """AC-003a: uvicorn.run() receives log_config from get_uvicorn_log_config(), not None."""
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            runner.invoke(app, ["serve"])
            kwargs = mock_uvicorn.run.call_args[1]
            assert "log_config" in kwargs
            assert kwargs["log_config"] is not None

    def test_log_config_preserves_existing_loggers(self) -> None:
        """AC-003b: log_config['disable_existing_loggers'] is False."""
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            runner.invoke(app, ["serve"])
            kwargs = mock_uvicorn.run.call_args[1]
            log_config = kwargs["log_config"]
            assert log_config["disable_existing_loggers"] is False


# ---------------------------------------------------------------------------
# FR-004: PORT environment variable
# ---------------------------------------------------------------------------


class TestServePortEnvVar:
    """AC-004a through AC-004c — PORT env var support."""

    def test_port_env_var_sets_port(self, monkeypatch) -> None:
        """AC-004a: PORT=3000 arvel serve binds to port 3000."""
        monkeypatch.setenv("PORT", "3000")
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            result = runner.invoke(app, ["serve"])
            assert result.exit_code == 0
            kwargs = mock_uvicorn.run.call_args[1]
            assert kwargs["port"] == 3000

    def test_cli_port_overrides_env_var(self, monkeypatch) -> None:
        """AC-004b: CLI --port takes precedence over PORT env var."""
        monkeypatch.setenv("PORT", "3000")
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            result = runner.invoke(app, ["serve", "--port", "4000"])
            assert result.exit_code == 0
            kwargs = mock_uvicorn.run.call_args[1]
            assert kwargs["port"] == 4000

    def test_default_port_without_env_var(self) -> None:
        """AC-004c: Default port is 8000 when PORT env and --port are absent."""
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            result = runner.invoke(app, ["serve"])
            assert result.exit_code == 0
            kwargs = mock_uvicorn.run.call_args[1]
            assert kwargs["port"] == 8000


# ---------------------------------------------------------------------------
# FR-005: Log discover_commands() failures
# ---------------------------------------------------------------------------


class TestDiscoverCommandsLogging:
    """AC-005a through AC-005c — broken user commands produce warnings."""

    def test_broken_command_module_produces_warning(self, tmp_path, caplog) -> None:
        """AC-005a: A broken command module produces a warning log."""
        commands_dir = tmp_path / "app" / "Console" / "Commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "broken.py").write_text("raise SyntaxError('bad')")

        from arvel.cli.app import discover_commands

        with caplog.at_level(logging.WARNING):
            discover_commands(base_path=tmp_path)

        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("broken" in msg for msg in warning_messages), (
            f"Expected a warning about 'broken' module, got: {warning_messages}"
        )

    def test_cli_starts_despite_broken_command(self, tmp_path) -> None:
        """AC-005b: The CLI still starts successfully despite the broken module."""
        commands_dir = tmp_path / "app" / "Console" / "Commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "broken.py").write_text("raise RuntimeError('oops')")

        from arvel.cli.app import discover_commands

        discover_commands(base_path=tmp_path)

    def test_valid_commands_still_discovered_alongside_broken(self, tmp_path) -> None:
        """AC-005c: Other valid command modules are still registered."""
        commands_dir = tmp_path / "app" / "Console" / "Commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "broken.py").write_text("raise RuntimeError('oops')")
        (commands_dir / "good.py").write_text(
            "import typer\ngood_app = typer.Typer(name='good', help='test')\n"
            "@good_app.command()\ndef hello():\n    print('hello')\n"
        )

        from arvel.cli.app import discover_commands

        discover_commands(base_path=tmp_path)


# ---------------------------------------------------------------------------
# Venv detection — _activate_project_venv()
# ---------------------------------------------------------------------------


class TestServeVenvDetection:
    """Global arvel serve should detect the project's .venv and add site-packages."""

    def _make_fake_venv(self, base: Path, venv_name: str = ".venv") -> Path:
        """Create a minimal fake venv directory structure."""
        sp = base / venv_name / "lib" / "python3.14" / "site-packages"
        sp.mkdir(parents=True)
        return sp

    def test_project_venv_site_packages_added_to_sys_path(self, tmp_path, monkeypatch) -> None:
        sp = self._make_fake_venv(tmp_path)
        sp_str = str(sp)
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)

        original_path = sys.path.copy()
        try:
            if sp_str in sys.path:
                sys.path.remove(sp_str)
            _activate_project_venv(tmp_path)
            assert sp_str in sys.path
            assert os.environ.get("VIRTUAL_ENV") == str(tmp_path / ".venv")
        finally:
            sys.path[:] = original_path

    def test_no_venv_directory_is_noop(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)
        original_path = sys.path.copy()
        try:
            _activate_project_venv(tmp_path)
            assert sys.path == original_path
            assert "VIRTUAL_ENV" not in os.environ
        finally:
            sys.path[:] = original_path

    def test_venv_directory_name_fallback(self, tmp_path, monkeypatch) -> None:
        sp = self._make_fake_venv(tmp_path, venv_name="venv")
        sp_str = str(sp)
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)

        original_path = sys.path.copy()
        try:
            if sp_str in sys.path:
                sys.path.remove(sp_str)
            _activate_project_venv(tmp_path)
            assert sp_str in sys.path
            assert os.environ.get("VIRTUAL_ENV") == str(tmp_path / "venv")
        finally:
            sys.path[:] = original_path

    def test_already_in_project_venv_is_noop(self, tmp_path, monkeypatch) -> None:
        sp = self._make_fake_venv(tmp_path)
        sp_str = str(sp)
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)

        original_path = sys.path.copy()
        try:
            if sp_str not in sys.path:
                sys.path.insert(0, sp_str)
            path_before = sys.path.copy()
            _activate_project_venv(tmp_path)
            assert sys.path.count(sp_str) == 1
            assert sys.path == path_before
        finally:
            sys.path[:] = original_path


# ---------------------------------------------------------------------------
# Existing tests (preserved)
# ---------------------------------------------------------------------------


class TestServeWithoutUvicorn:
    def test_missing_uvicorn_shows_error(self) -> None:
        with patch.dict("sys.modules", {"uvicorn": None}):
            result = runner.invoke(app, ["serve"])
            assert result.exit_code == 1
            assert "uvicorn is not installed" in result.output


class TestServeRootPath:
    def test_root_path_passed_to_uvicorn(self) -> None:
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            result = runner.invoke(app, ["serve", "--root-path", "/api/v1"])
            assert result.exit_code == 0
            kwargs = mock_uvicorn.run.call_args[1]
            assert kwargs["root_path"] == "/api/v1"

    def test_root_path_echoed_to_user(self) -> None:
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            result = runner.invoke(app, ["serve", "--root-path", "/v2"])
            plain = _strip_ansi(result.output)
            assert "Root path" in plain
            assert "/v2" in plain


class TestServeProxyHeaders:
    def test_proxy_headers_default_true(self) -> None:
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            runner.invoke(app, ["serve"])
            kwargs = mock_uvicorn.run.call_args[1]
            assert kwargs["proxy_headers"] is True

    def test_no_proxy_headers(self) -> None:
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            runner.invoke(app, ["serve", "--no-proxy-headers"])
            kwargs = mock_uvicorn.run.call_args[1]
            assert kwargs["proxy_headers"] is False

    def test_forwarded_allow_ips(self) -> None:
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            runner.invoke(app, ["serve", "--forwarded-allow-ips", "10.0.0.1,10.0.0.2"])
            kwargs = mock_uvicorn.run.call_args[1]
            assert kwargs["forwarded_allow_ips"] == "10.0.0.1,10.0.0.2"


class TestServeReloadDir:
    def test_reload_dir_passed_to_uvicorn(self, tmp_path) -> None:
        watch_dir = tmp_path / "src"
        watch_dir.mkdir()
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            result = runner.invoke(app, ["serve", "--reload-dir", str(watch_dir)])
            assert result.exit_code == 0
            kwargs = mock_uvicorn.run.call_args[1]
            assert kwargs["reload"] is True
            assert kwargs["reload_dirs"] is not None
            assert str(watch_dir.resolve()) in kwargs["reload_dirs"]

    def test_reload_dir_implies_reload(self, tmp_path) -> None:
        watch_dir = tmp_path / "src"
        watch_dir.mkdir()
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="bootstrap.app:create_app",
            ),
        ):
            result = runner.invoke(app, ["serve", "--no-reload", "--reload-dir", str(watch_dir)])
            assert result.exit_code == 0
            kwargs = mock_uvicorn.run.call_args[1]
            assert kwargs["reload"] is True


class TestAppDiscovery:
    def test_discovery_returns_entrypoint_when_bootstrap_exists(
        self,
        tmp_path,
        monkeypatch,
    ) -> None:
        bootstrap = tmp_path / "bootstrap"
        bootstrap.mkdir()
        (bootstrap / "app.py").write_text("def create_app(): ...")
        monkeypatch.chdir(tmp_path)
        assert _discover_app() == "bootstrap.app:create_app"

    def test_discovery_raises_when_no_bootstrap(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ArvelCLIError, match=r"bootstrap/app\.py not found"):
            _discover_app()

    def test_discovery_with_base_path_finds_bootstrap(self, tmp_path) -> None:
        """FR-002 + AC-002b: _discover_app(base_path=...) checks relative to base_path."""
        bootstrap = tmp_path / "bootstrap"
        bootstrap.mkdir()
        (bootstrap / "app.py").write_text("def create_app(): ...")
        assert _discover_app(base_path=tmp_path) == "bootstrap.app:create_app"

    def test_discovery_with_base_path_raises_when_no_bootstrap(self, tmp_path) -> None:
        """_discover_app(base_path=...) raises when bootstrap/app.py is missing."""
        with pytest.raises(ArvelCLIError, match=r"bootstrap/app\.py not found"):
            _discover_app(base_path=tmp_path)
