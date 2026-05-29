"""S-005-04..09 — Operational commands.

AC covered:
  AC-005-006-01  migrate runs pending migrations
  AC-005-006-02  migrate exits 0 when nothing to migrate
  AC-005-007-01  migrate:rollback reverts last batch
  AC-005-008-01  migrate:status lists all migrations with applied/pending status
  AC-005-009-01  route:list exits 0 and outputs a table
  AC-005-009-02  route:list shows method, path, handler columns
  AC-005-011-01  db:seed runs the DatabaseSeeder by default
  AC-005-011-02  db:seed --seeder=<Name> runs the named seeder class
  AC-005-012-01  key:rotate exits 2 when APP_ENV=production and --force not set
  AC-005-012-02  key:rotate exits 0 on success and prints RotationResult
  AC-005-012-03  key:rotate --force bypasses APP_ENV guard
  SEC-005-001    key:rotate production guard
  AC-005-013-01  about exits 0 and prints arvel version
  AC-005-013-02  about prints Python version
  AC-005-014-01  shell exits 0 with --dry-run flag
  AC-005-014-02  shell uses IPython when available, falls back to code.interact
  SEC-005-002    shell does not bootstrap Application in unsafe environment
"""

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


# ─── AC-005-006-01 / AC-005-006-02: migrate ──────────────────────────────────


def test_migrate_exits_zero_with_no_pending(tmp_path: Any) -> None:
    """AC-005-006-02: migrate exits 0 when there are no pending migrations."""
    app = _app(MigrateCommand())
    with patch(
        "arvel.console.commands.migrate.MigrateCommand._run_migrations", new_callable=AsyncMock
    ) as mock:
        mock.return_value = 0
        result = runner.invoke(app.typer_app, ["migrate"])
        assert result.exit_code == 0


def test_migrate_calls_run_migrations(tmp_path: Any) -> None:
    """AC-005-006-01: migrate invokes the migration runner."""
    app = _app(MigrateCommand())
    with patch(
        "arvel.console.commands.migrate.MigrateCommand._run_migrations", new_callable=AsyncMock
    ) as mock:
        mock.return_value = ["migration_001", "migration_002", "migration_003"]
        invoke_async(runner, app.typer_app, ["migrate"])
        mock.assert_awaited_once()


# NOTE: migrate:rollback / migrate:status / db:seed real-wire-up coverage
# lives in tests/console/test_migrate_db_seed_real.py (WI-arvel-022).
# The old stub-era mock tests were removed when the real Migrator landed.


# ─── AC-005-009-01 / AC-005-009-02: route:list ───────────────────────────────


def test_route_list_exits_zero() -> None:
    """AC-005-009-01: route:list exits 0."""
    app = _app(RouteListCommand())
    with patch("arvel.console.commands.route_list.RouteListCommand.get_routes") as mock:
        mock.return_value = []
        result = runner.invoke(app.typer_app, ["route:list"])
        assert result.exit_code == 0


def test_route_list_shows_method_path_handler_columns() -> None:
    """AC-005-009-02: route:list table includes method, path, handler columns."""
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
# tests/console/test_migrate_db_seed_real.py (WI-arvel-022).


# ─── SEC-005-001 / FR-021-08: key:rotate ────────────────────────────────────
# WI-021 / ADR — key:rotate is honest-deferred. The previous "rotate then
# print RotationResult" tests assumed a working implementation; that work is
# tracked in FB-022-002. Only the production guard and the deferral exit
# code are validated here.


def test_key_rotate_exits_2_in_production_without_force(clean_env: Any) -> None:
    """SEC-005-001: key:rotate exits 2 when APP_ENV=production."""
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
    """FR-021-08: outside production, exits 2 with FB-022-002 pointer (no false success)."""
    os.environ["APP_ENV"] = "local"
    app = _app(KeyRotateCommand())
    result = runner.invoke(
        app.typer_app,
        ["key:rotate", "--old-key", "AAAA", "--new-key", "BBBB"],
    )
    assert result.exit_code == 2
    assert "FB-022-002" in (result.stderr or result.output)


# ─── AC-005-013-01 / AC-005-013-02: about ───────────────────────────────────


def test_about_exits_zero() -> None:
    """AC-005-013-01: about exits 0."""
    app = _app(AboutCommand())
    result = runner.invoke(app.typer_app, ["about"])
    assert result.exit_code == 0


def test_about_prints_arvel_version() -> None:
    """AC-005-013-01: about prints the arvel version string."""
    app = _app(AboutCommand())
    result = runner.invoke(app.typer_app, ["about"])
    assert "arvel" in result.output.lower()


def test_about_prints_python_version() -> None:
    """AC-005-013-02: about prints the Python version."""
    import sys

    app = _app(AboutCommand())
    result = runner.invoke(app.typer_app, ["about"])
    major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert major_minor in result.output


# ─── AC-005-014-01 / AC-005-014-02 / SEC-005-002: shell ─────────────────────


def test_shell_dry_run_exits_zero() -> None:
    """AC-005-014-01: shell --dry-run exits 0 without launching a REPL."""
    app = _app(ShellCommand())
    result = runner.invoke(app.typer_app, ["shell", "--dry-run"])
    assert result.exit_code == 0


def test_shell_uses_ipython_when_available(monkeypatch: Any) -> None:
    """AC-005-014-02: shell uses IPython.embed() with the built namespace as user_ns.

    The kwarg name matters: IPython.embed() only honours ``user_ns``, not
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
    """AC-005-014-02: shell falls back to code.interact() when IPython is absent."""
    with (
        patch.dict("sys.modules", {"IPython": None}),
        patch("arvel.console.commands.shell.ShellCommand.build_namespace") as boot,
        patch("code.interact") as interact_mock,
    ):
        boot.return_value = MagicMock()
        app = _app(ShellCommand())
        runner.invoke(app.typer_app, ["shell"])
        interact_mock.assert_called_once()
