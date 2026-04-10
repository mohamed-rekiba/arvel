"""Tests for arvel serve command."""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from arvel.cli.app import app
from arvel.cli.commands.serve import _discover_app
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


class TestServeDefaultOptions:
    def test_serve_invokes_uvicorn_with_defaults(self) -> None:
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="app.main:create_app",
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
                return_value="app.main:create_app",
            ),
        ):
            result = runner.invoke(app, ["serve", "--port", "3000"])
            assert result.exit_code == 0
            kwargs = mock_uvicorn.run.call_args[1]
            assert kwargs["port"] == 3000


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
                return_value="app.main:create_app",
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
                return_value="app.main:app",
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
                return_value="app.main:app",
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
                return_value="app.main:app",
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
                return_value="app.main:app",
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
                return_value="app.main:app",
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
                return_value="app.main:app",
            ),
        ):
            result = runner.invoke(app, ["serve", "--no-reload", "--reload-dir", str(watch_dir)])
            assert result.exit_code == 0
            kwargs = mock_uvicorn.run.call_args[1]
            assert kwargs["reload"] is True


class TestServeLogConfig:
    def test_log_config_none_defers_to_arvel_logging(self) -> None:
        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch(
                "arvel.cli.commands.serve._discover_app",
                return_value="app.main:app",
            ),
        ):
            runner.invoke(app, ["serve"])
            kwargs = mock_uvicorn.run.call_args[1]
            assert "log_config" in kwargs
            assert kwargs["log_config"] is None


class TestServeExplicitApp:
    def test_explicit_app_skips_discovery(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            result = runner.invoke(app, ["serve", "--app", "mymodule:myapp"])
            assert result.exit_code == 0
            call_args = mock_uvicorn.run.call_args
            import_string = call_args[0][0] if call_args[0] else call_args[1].get("app")
            assert import_string == "mymodule:myapp"


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
