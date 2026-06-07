"""Operational console commands — migrate, route:list, key:rotate, about, shell."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from arvel.console import Application, Command
from arvel.console.commands.about import AboutCommand
from arvel.console.commands.key_rotate import KeyRotateCommand
from arvel.console.commands.migrate import MigrateCommand
from arvel.console.commands.route_list import RouteListCommand
from arvel.console.commands.shell import ShellCommand
from typer.testing import CliRunner

from .conftest import invoke_async

runner = CliRunner()


def _app(*cmds: Command) -> Application:
    return Application(commands=list(cmds))


# ─── migrate ──────────────────────────────────


def test_migrate_exits_zero_with_no_pending(tmp_path: Any) -> None:
    """migrate exits 0 when there are no pending migrations."""
    app = _app(MigrateCommand())
    with patch(
        "arvel.console.commands.migrate.MigrateCommand._run_migrations", new_callable=AsyncMock
    ) as mock:
        mock.return_value = 0
        result = runner.invoke(app.typer_app, ["migrate"])
        assert result.exit_code == 0


def test_migrate_calls_run_migrations(tmp_path: Any) -> None:
    """migrate invokes the migration runner."""
    app = _app(MigrateCommand())
    with patch(
        "arvel.console.commands.migrate.MigrateCommand._run_migrations", new_callable=AsyncMock
    ) as mock:
        mock.return_value = ["migration_001", "migration_002", "migration_003"]
        invoke_async(runner, app.typer_app, ["migrate"])
        mock.assert_awaited_once()


# NOTE: migrate:rollback / migrate:status / db:seed real-wire-up coverage
# lives in tests/console/test_migrate_db_seed_real.py.
# The old stub-era mock tests were removed when the real Migrator landed.


# ─── route:list ───────────────────────────────


def test_route_list_exits_zero() -> None:
    """route:list exits 0."""
    app = _app(RouteListCommand())
    with patch("arvel.console.commands.route_list.RouteListCommand.get_routes") as mock:
        mock.return_value = []
        result = runner.invoke(app.typer_app, ["route:list"])
        assert result.exit_code == 0


def test_route_list_shows_method_path_handler_columns() -> None:
    """route:list table includes method, path, handler columns."""
    from arvel.routing import RouteSpec

    async def _stub_handler() -> None: ...

    app = _app(RouteListCommand())
    with patch("arvel.console.commands.route_list.RouteListCommand.get_routes") as mock:
        mock.return_value = [
            RouteSpec(
                method="GET",
                path="/articles",
                handler=_stub_handler,
                name="articles.index",
            ),
        ]
        result = runner.invoke(app.typer_app, ["route:list"])
        assert "GET" in result.output
        assert "/articles" in result.output
        assert "_stub_handler" in result.output


# NOTE: db:seed coverage with real seeder discovery lives in
# tests/console/test_migrate_db_seed_real.py.


# ─── key:rotate ────────────────────────────────────
# key:rotate is honest-deferred — rotation isn't implemented yet.
# Only the production guard and deferral exit code are validated here.


def test_key_rotate_exits_2_in_production_without_force(clean_env: Any) -> None:
    """key:rotate exits 2 when APP_ENV=production."""
    os.environ["APP_ENV"] = "production"
    app = _app(KeyRotateCommand())
    result = runner.invoke(
        app.typer_app,
        ["key:rotate", "--old-key", "AAAA", "--new-key", "BBBB"],
    )
    assert result.exit_code == 2


def test_key_rotate_exits_2_outside_production_with_deferral_message(
    clean_env: Any,
) -> None:
    """outside production, exits 2 with pointer (no false success)."""
    os.environ["APP_ENV"] = "local"
    app = _app(KeyRotateCommand())
    result = runner.invoke(
        app.typer_app,
        ["key:rotate", "--old-key", "AAAA", "--new-key", "BBBB"],
    )
    assert result.exit_code == 2
    output = result.stderr or result.output
    assert "not yet implemented" in output.lower()
    assert "workaround" in output.lower()


# ─── about ───────────────────────────────────


def test_about_exits_zero() -> None:
    """about exits 0."""
    app = _app(AboutCommand())
    result = runner.invoke(app.typer_app, ["about"])
    assert result.exit_code == 0


def test_about_prints_arvel_version() -> None:
    """about prints the arvel version string."""
    app = _app(AboutCommand())
    result = runner.invoke(app.typer_app, ["about"])
    assert "arvel" in result.output.lower()


def test_about_prints_python_version() -> None:
    """about prints the Python version."""
    import sys

    app = _app(AboutCommand())
    result = runner.invoke(app.typer_app, ["about"])
    major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert major_minor in result.output


# ─── shell ─────────────────────


def test_shell_dry_run_exits_zero() -> None:
    """shell --dry-run exits 0 without launching a REPL."""
    app = _app(ShellCommand())
    result = runner.invoke(app.typer_app, ["shell", "--dry-run"])
    assert result.exit_code == 0


def test_shell_uses_ipython_when_available(monkeypatch: Any) -> None:
    """shell uses IPython.embed with the built namespace as user_ns.

    The kwarg name matters: IPython.embed only honours ``user_ns``, not
    ``local_ns`` — passing the wrong name silently drops the namespace and
    leaves the REPL to fall back to the caller's frame globals.
    """

    app = _app(ShellCommand())
    ipython_mock = MagicMock()
    namespace_mock = MagicMock()

    with patch.dict("sys.modules", {"IPython": ipython_mock}):
        with patch("arvel.console.commands.shell.ShellCommand.build_namespace") as boot:
            boot.return_value = namespace_mock
            runner.invoke(app.typer_app, ["shell"])
        ipython_mock.embed.assert_called_once()
        embed_kwargs = ipython_mock.embed.call_args.kwargs
        assert "user_ns" in embed_kwargs, (
            f"embed() must be called with user_ns=... got kwargs: {list(embed_kwargs)}"
        )
        assert embed_kwargs["user_ns"] is namespace_mock
        assert "local_ns" not in embed_kwargs, (
            "embed(local_ns=...) is silently dropped by IPython — use user_ns"
        )


def test_shell_falls_back_to_code_interact_without_ipython(monkeypatch: Any) -> None:
    """shell falls back to code.interact when IPython is absent."""
    with (
        patch.dict("sys.modules", {"IPython": None}),
        patch("arvel.console.commands.shell.ShellCommand.build_namespace") as boot,
        patch("code.interact") as interact_mock,
    ):
        boot.return_value = MagicMock()
        app = _app(ShellCommand())
        runner.invoke(app.typer_app, ["shell"])
        interact_mock.assert_called_once()
