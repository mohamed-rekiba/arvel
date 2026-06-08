"""Migration reset family (migrate:fresh, migrate:reset, migrate:refresh).

 migrate:reset with no applied migrations exits 0
 migrate:reset rolls back applied migrations in reverse order
 migrate:fresh drops all tables and re-runs migrations
 migrate:fresh --seed invokes db:seed after migrating
 migrate:refresh is equivalent to reset && migrate
 migrate:fresh refuses in production without ARVEL_ALLOW_DESTRUCTIVE=1

Uses a real in-memory SQLite engine wired through a hand-rolled framework
Application — mirroring the test_migrate_db_seed_real.py pattern.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from arvel.console import Application, Command
from arvel.console.commands.migrate_fresh import MigrateFreshCommand
from arvel.console.commands.migrate_refresh import MigrateRefreshCommand
from arvel.console.commands.migrate_reset import MigrateResetCommand
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from typer.testing import CliRunner

from .conftest import invoke_async

runner = CliRunner()


_NOOP_UP = '''"""No-op migration."""

from arvel.database import Schema


async def up(schema: Schema) -> None:
    return


async def down(schema: Schema) -> None:
    return
'''


def _make_app_with_engine(tmp_path: Path, engine: AsyncEngine, *cmds: Command) -> Application:
    """Mirror test_migrate_db_seed_real._make_app_with_engine — bind AsyncEngine
    via a hand-rolled framework Application + container."""

    class _FakeContainer:
        def __init__(self, engine: AsyncEngine, base_path: Path) -> None:
            self._engine = engine
            self._base = base_path

        def make(self, key: object) -> object:
            if key is AsyncEngine:
                return self._engine
            raise KeyError(key)

    class _FakeFrameworkApp:
        def __init__(self, engine: AsyncEngine, base_path: Path) -> None:
            self.container = _FakeContainer(engine, base_path)
            self._base = base_path

        def base_path(self) -> Path:
            return self._base

    fake_app = _FakeFrameworkApp(engine, tmp_path)
    for cmd in cmds:
        cmd.app = fake_app  # type: ignore[assignment] — Command.app is the seam from

    return Application(commands=list(cmds))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "database" / "migrations").mkdir(parents=True)
    (tmp_path / "database" / "seeders").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def engine() -> Iterator[AsyncEngine]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        yield eng
    finally:
        asyncio.run(eng.dispose())


# ─── — reset with nothing applied ────────────────────────────────────


def test_migrate_reset_with_nothing_applied_exits_zero(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, MigrateResetCommand())
    result = invoke_async(runner, app.typer_app, ["migrate:reset"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "nothing" in result.stdout.lower()


# ─── — reset rolls back applied migrations in reverse order ─────────


def test_migrate_reset_rolls_back_in_reverse_order(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / "database" / "migrations" / "2026_01_01_a.py").write_text(_NOOP_UP)
    (project / "database" / "migrations" / "2026_01_02_b.py").write_text(_NOOP_UP)
    monkeypatch.chdir(project)
    # Apply both first via the real migrator
    import asyncio

    from arvel.database.migrator import Migrator

    asyncio.run(_apply_all(Migrator(engine, project / "database" / "migrations")))

    app = _make_app_with_engine(project, engine, MigrateResetCommand())
    result = invoke_async(runner, app.typer_app, ["migrate:reset"])
    assert result.exit_code == 0, result.stdout + result.stderr
    # Both migrations get rolled back, reverse order printed
    assert "2026_01_02_b" in result.stdout
    assert "2026_01_01_a" in result.stdout
    assert result.stdout.index("2026_01_02_b") < result.stdout.index("2026_01_01_a")


async def _apply_all(migrator: Any) -> None:
    await migrator.ensure_table()
    await migrator.upgrade()


# ─── — fresh drops all tables and re-runs migrations ─────────────────


def test_migrate_fresh_drops_all_then_migrates(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / "database" / "migrations" / "2026_01_01_a.py").write_text(_NOOP_UP)
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, MigrateFreshCommand())
    result = invoke_async(runner, app.typer_app, ["migrate:fresh"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "2026_01_01_a" in result.stdout


# ─── — fresh --seed invokes db:seed ──────────────────────────────────


def test_migrate_fresh_with_seed_invokes_db_seed(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(project)

    seed_invoked = False

    async def fake_db_seed_invoke(seeder: str | None = None, *, app: object) -> None:
        nonlocal seed_invoked
        seed_invoked = True

    monkeypatch.setattr(
        "arvel.console.commands.migrate_fresh.invoke_db_seed",
        fake_db_seed_invoke,
    )
    app = _make_app_with_engine(project, engine, MigrateFreshCommand())
    result = invoke_async(runner, app.typer_app, ["migrate:fresh", "--seed"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert seed_invoked


# ─── — refresh is reset && migrate ───────────────────────────────────


def test_migrate_refresh_resets_then_reapplies(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / "database" / "migrations" / "2026_01_01_a.py").write_text(_NOOP_UP)
    monkeypatch.chdir(project)
    # First apply once
    import asyncio

    from arvel.database.migrator import Migrator

    asyncio.run(_apply_all(Migrator(engine, project / "database" / "migrations")))

    app = _make_app_with_engine(project, engine, MigrateRefreshCommand())
    result = invoke_async(runner, app.typer_app, ["migrate:refresh"])
    assert result.exit_code == 0, result.stdout + result.stderr
    # Migration name should appear (re-applied after rollback)
    assert "2026_01_01_a" in result.stdout


# ─── — production guard ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "command_cls",
    [MigrateFreshCommand, MigrateRefreshCommand],
)
def test_destructive_command_refuses_in_production(
    command_cls: type[Command],
    project: Path,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from arvel.config._lookup_registry import register

    register("app", SimpleNamespace(env="production", is_production=True))
    monkeypatch.delenv("ARVEL_ALLOW_DESTRUCTIVE", raising=False)
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, command_cls())
    result = invoke_async(runner, app.typer_app, [command_cls.name])
    assert result.exit_code == 2, result.stdout + result.stderr
    assert "production" in (result.stdout + result.stderr).lower()


@pytest.mark.parametrize(
    ("command_cls", "module"),
    [
        (MigrateFreshCommand, "arvel.console.commands.migrate_fresh"),
        (MigrateRefreshCommand, "arvel.console.commands.migrate_refresh"),
    ],
)
def test_destructive_command_exits_2_when_database_unavailable(
    command_cls: type[Command],
    module: str,
    project: Path,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from arvel.config._lookup_registry import register
    from arvel.database.health import DatabaseUnavailableError

    # Non-production so the destructive guard doesn't short-circuit before the DB check.
    register("app", SimpleNamespace(env="testing", is_production=False))

    async def _down(_engine: object) -> None:
        raise DatabaseUnavailableError("cannot connect to the database: refused")

    monkeypatch.setattr(f"{module}.check_database_connection", _down)
    monkeypatch.delenv("ARVEL_ALLOW_DESTRUCTIVE", raising=False)
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, command_cls())
    result = invoke_async(runner, app.typer_app, [command_cls.name])
    assert result.exit_code == 2, result.stdout + result.stderr
    assert "database is not available" in (result.stdout + result.stderr).lower()


@pytest.mark.parametrize(
    "command_cls",
    [MigrateFreshCommand, MigrateRefreshCommand],
)
def test_destructive_command_runs_in_production_with_override(
    command_cls: type[Command],
    project: Path,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from arvel.config._lookup_registry import register

    register("app", SimpleNamespace(env="production", is_production=True))
    monkeypatch.setenv("ARVEL_ALLOW_DESTRUCTIVE", "1")
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, command_cls())
    result = invoke_async(runner, app.typer_app, [command_cls.name])
    assert result.exit_code == 0, result.stdout + result.stderr
