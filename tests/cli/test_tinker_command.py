"""Tests for FR-020-01: Interactive REPL (arvel tinker).

All tests are written BEFORE implementation (QA-Pre / Stage 3a).
They must compile but FAIL until the implementation is complete.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from arvel.cli.app import app

if TYPE_CHECKING:
    import pytest

runner = CliRunner()


def _tinker_namespace_fixture() -> dict[str, MagicMock]:
    """Minimal namespace so tinker tests skip real ``Application.create``."""
    mock_app = MagicMock()
    mock_app.shutdown = AsyncMock()
    return {
        "app": mock_app,
        "container": MagicMock(),
        "config": MagicMock(),
    }


class TestTinkerCommandRegistered:
    """FR-020-01: tinker command is accessible."""

    def test_tinker_help(self) -> None:
        result = runner.invoke(app, ["tinker", "--help"])
        assert result.exit_code == 0
        assert "tinker" in result.output.lower() or "repl" in result.output.lower()


class TestTinkerBootstrapsApp:
    """FR-020-01.1: tinker bootstraps the application."""

    def test_tinker_imports_from_module(self) -> None:
        from arvel.cli.plugins import tinker  # noqa: F401

    def test_tinker_starts_repl(self) -> None:
        ns = _tinker_namespace_fixture()
        with (
            patch("arvel.cli.plugins.tinker._build_namespace", return_value=ns),
            patch("arvel.cli.plugins.tinker._start_repl") as mock_repl,
        ):
            mock_repl.return_value = None
            result = runner.invoke(app, ["tinker"])
            assert result.exit_code == 0
            mock_repl.assert_called_once()


class TestTinkerNamespace:
    """FR-020-01.2: REPL pre-loads app, container, session into namespace."""

    def test_tinker_namespace_contains_app(self) -> None:
        ns = _tinker_namespace_fixture()
        with (
            patch("arvel.cli.plugins.tinker._build_namespace", return_value=ns),
            patch("arvel.cli.plugins.tinker._start_repl") as mock_repl,
        ):
            mock_repl.return_value = None
            runner.invoke(app, ["tinker"])
            call_args = mock_repl.call_args
            namespace = call_args[0][0] if call_args[0] else call_args[1].get("namespace", {})
            assert "app" in namespace

    def test_tinker_namespace_contains_container(self) -> None:
        ns = _tinker_namespace_fixture()
        with (
            patch("arvel.cli.plugins.tinker._build_namespace", return_value=ns),
            patch("arvel.cli.plugins.tinker._start_repl") as mock_repl,
        ):
            mock_repl.return_value = None
            runner.invoke(app, ["tinker"])
            call_args = mock_repl.call_args
            namespace = call_args[0][0] if call_args[0] else call_args[1].get("namespace", {})
            assert "container" in namespace


class TestTinkerIPythonDetection:
    """FR-020-01.3: IPython used if installed, stdlib fallback otherwise."""

    def test_tinker_uses_ipython_when_available(self) -> None:
        mock_ipython = MagicMock()
        ns = _tinker_namespace_fixture()
        with (
            patch("arvel.cli.plugins.tinker._build_namespace", return_value=ns),
            patch("arvel.cli.plugins.tinker._start_repl") as mock_repl,
            patch.dict("sys.modules", {"IPython": mock_ipython}),
        ):
            mock_repl.return_value = None
            result = runner.invoke(app, ["tinker"])
            assert result.exit_code == 0

    def test_tinker_falls_back_to_stdlib_repl(self) -> None:
        ns = _tinker_namespace_fixture()
        with (
            patch("arvel.cli.plugins.tinker._build_namespace", return_value=ns),
            patch("arvel.cli.plugins.tinker._start_repl") as mock_repl,
            patch.dict("sys.modules", {"IPython": None}),
        ):
            mock_repl.return_value = None
            result = runner.invoke(app, ["tinker"])
            assert result.exit_code == 0


class TestTinkerExecuteFlag:
    """FR-020-01.4: --execute evaluates expression non-interactively."""

    def test_tinker_execute_prints_result(self) -> None:
        result = runner.invoke(app, ["tinker", "--execute", "1 + 1"])
        assert result.exit_code == 0
        assert "2" in result.output

    def test_tinker_execute_with_string_expression(self) -> None:
        result = runner.invoke(app, ["tinker", "--execute", "'hello'.upper()"])
        assert result.exit_code == 0
        assert "HELLO" in result.output


class TestTinkerProductionGuard:
    """FR-020-01.5: tinker blocked in production unless --force."""

    def test_tinker_blocked_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        result = runner.invoke(app, ["tinker"])
        assert result.exit_code != 0
        output_lower = result.output.lower()
        assert (
            "production" in output_lower or "blocked" in output_lower or "disabled" in output_lower
        )

    def test_tinker_allowed_in_production_with_force(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        ns = _tinker_namespace_fixture()
        with (
            patch("arvel.cli.plugins.tinker._build_namespace", return_value=ns),
            patch("arvel.cli.plugins.tinker._start_repl") as mock_repl,
        ):
            mock_repl.return_value = None
            result = runner.invoke(app, ["tinker", "--force"])
            assert result.exit_code == 0

    def test_tinker_allowed_in_development(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "development")
        ns = _tinker_namespace_fixture()
        with (
            patch("arvel.cli.plugins.tinker._build_namespace", return_value=ns),
            patch("arvel.cli.plugins.tinker._start_repl") as mock_repl,
        ):
            mock_repl.return_value = None
            result = runner.invoke(app, ["tinker"])
            assert result.exit_code == 0


class TestTinkerGracefulShutdown:
    """FR-020-01.6: Database connections closed on exit."""

    def test_tinker_calls_shutdown_on_exit(self) -> None:
        mock_shutdown = MagicMock()
        ns = _tinker_namespace_fixture()
        with (
            patch("arvel.cli.plugins.tinker._build_namespace", return_value=ns),
            patch("arvel.cli.plugins.tinker._start_repl") as mock_repl,
        ):
            mock_repl.return_value = None
            with patch("arvel.cli.plugins.tinker._shutdown", mock_shutdown):
                runner.invoke(app, ["tinker"])
                mock_shutdown.assert_called_once()
