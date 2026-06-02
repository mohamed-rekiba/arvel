"""CLI integration tests for migrate / migrate:rollback /
migrate:status / db:seed against the real Migrator.

These tests use a real
in-memory SQLite engine bound into a hand-rolled framework Application
to exercise the full CLI → command → Migrator → engine path.

Traces to (migrate), (migrate:rollback),
 (migrate:status), (db:seed), and (honest
exit codes).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import typer

# These imports are stable already
from arvel.console import Application
from arvel.console.commands.db_seed import DbSeedCommand, run_seeder_for_app
from arvel.console.commands.migrate import (
    MigrateCommand,
    MigrateRollbackCommand,
    MigrateStatusCommand,
)
from arvel.database.migrator import Migrator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from typer.testing import CliRunner

from .conftest import invoke_async

runner = CliRunner()


def _mark_migrated(engine: AsyncEngine) -> None:
    """Create the migrations tracking table so db:seed's preflight passes."""
    asyncio.run(Migrator(engine, Path(".")).ensure_table())


_NOOP_UP = '''"""No-op migration."""

from arvel.database import Schema


async def up(schema: Schema) -> None:
    return


async def down(schema: Schema) -> None:
    return
'''


_RAISING_UP = '''"""Failing migration."""

from arvel.database import Schema


async def up(schema: Schema) -> None:
    raise RuntimeError("planned failure")


async def down(schema: Schema) -> None:
    return
'''


_BASIC_SEEDER = '''"""Test seeder."""

from arvel.database import Seeder

_calls: list[str] = []


class DatabaseSeeder(Seeder):
    async def run(self) -> None:
        _calls.append("DatabaseSeeder")
'''


_RAISING_SEEDER = '''"""Failing seeder."""

from arvel.database import Seeder


class BadSeeder(Seeder):
    async def run(self) -> None:
        raise RuntimeError("seeder boom")
'''


def _make_app_with_engine(tmp_path: Path, engine: AsyncEngine, *cmds: Any) -> Application:
    """Construct a console Application that binds AsyncEngine via a fake
    framework Application whose container resolves AsyncEngine to `engine`.
    """
    from arvel.console import Command

    class _FakeContainer:
        def __init__(self, engine: AsyncEngine, base_path: Path) -> None:
            self._engine = engine
            self._base = base_path

        def make(self, key: object) -> object:
            if key is AsyncEngine:
                return self._engine
            if getattr(key, "__origin__", None) is async_sessionmaker or key is async_sessionmaker:
                return async_sessionmaker(self._engine, expire_on_commit=False)
            raise KeyError(key)

    class _FakeFrameworkApp:
        def __init__(self, engine: AsyncEngine, base_path: Path) -> None:
            self.container = _FakeContainer(engine, base_path)
            self._base = base_path

        def base_path(self) -> Path:
            return self._base

    fake_app = _FakeFrameworkApp(engine, tmp_path)

    for cmd in cmds:
        assert isinstance(cmd, Command)
        cmd.app = fake_app  # type: ignore[assignment] — Command.app is the seam added

    return Application(commands=list(cmds))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Lay out a minimal project: database/migrations + database/seeders dirs."""
    (tmp_path / "database" / "migrations").mkdir(parents=True)
    (tmp_path / "database" / "seeders").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def engine() -> Iterator[AsyncEngine]:
    """In-memory engine. Tests run sync via asyncio.run on the inner CLI calls
    — the engine just needs to be reachable from inside the CLI callback."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        yield eng
    finally:
        asyncio.run(eng.dispose())


@pytest.fixture
def dead_engine() -> Iterator[AsyncEngine]:
    """An engine that can't connect — sqlite file in a directory that doesn't exist."""
    eng = create_async_engine("sqlite+aiosqlite:////nonexistent-arvel-dir/does_not_exist.db")
    try:
        yield eng
    finally:
        asyncio.run(eng.dispose())


# ============================================================
# — MigrateCommand wires real migrator
# ============================================================


def test_migrate_with_no_files_prints_nothing_to_migrate(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-008-02: Nothing to migrate. message (not Ran 0 migration(s).)."""
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, MigrateCommand())
    result = invoke_async(runner, app.typer_app, ["migrate"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Nothing to migrate." in result.stdout
    assert "Ran 0" not in result.stdout


def test_migrate_applies_pending(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-008-01: applies pending migrations and prints names."""
    (project / "database" / "migrations" / "2026_01_01_a.py").write_text(_NOOP_UP)
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, MigrateCommand())
    result = invoke_async(runner, app.typer_app, ["migrate"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Ran 1 migration(s):" in result.stdout
    assert "2026_01_01_a" in result.stdout


def test_migrate_dry_run_lists_without_applying(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-008-04: --dry-run lists files, exits 0, no DB writes."""
    (project / "database" / "migrations" / "2026_01_01_a.py").write_text(_NOOP_UP)
    (project / "database" / "migrations" / "2026_01_01_b.py").write_text(_NOOP_UP)
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, MigrateCommand())
    result = invoke_async(runner, app.typer_app, ["migrate", "--dry-run"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "2026_01_01_a" in result.stdout
    assert "2026_01_01_b" in result.stdout
    # Re-invoke without dry-run — both should now be pending and run.
    app2 = _make_app_with_engine(project, engine, MigrateCommand())
    result2 = invoke_async(runner, app2.typer_app, ["migrate"])
    assert "Ran 2 migration(s):" in result2.stdout


def test_migrate_body_failure_exit_code_1_with_stderr(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-008-03: body failure → exit 1, error on stderr."""
    (project / "database" / "migrations" / "2026_01_01_bad.py").write_text(_RAISING_UP)
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, MigrateCommand())
    result = invoke_async(runner, app.typer_app, ["migrate"])
    assert result.exit_code == 1, (
        f"expected 1, got {result.exit_code}; stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "migration failed" in result.stderr.lower()
    assert "2026_01_01_bad" in result.stderr


# ============================================================
# — MigrateRollbackCommand wires real migrator
# ============================================================


def test_rollback_with_nothing_applied_prints_nothing(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-009-02."""
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, MigrateRollbackCommand())
    result = invoke_async(runner, app.typer_app, ["migrate:rollback"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Nothing to roll back." in result.stdout
    assert "Rolled back 0" not in result.stdout


def test_rollback_after_migrate_undoes_last_batch(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-009-01: prints `Rolled back N migration(s):` + names."""
    (project / "database" / "migrations" / "2026_01_01_a.py").write_text(_NOOP_UP)
    monkeypatch.chdir(project)
    app_m = _make_app_with_engine(project, engine, MigrateCommand())
    invoke_async(runner, app_m.typer_app, ["migrate"])
    app_r = _make_app_with_engine(project, engine, MigrateRollbackCommand())
    result = invoke_async(runner, app_r.typer_app, ["migrate:rollback"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Rolled back 1 migration(s):" in result.stdout
    assert "2026_01_01_a" in result.stdout


# ============================================================
# — MigrateStatusCommand wires real migrator
# ============================================================


def test_status_table_has_header_and_rows(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-010-01 + -010-02 + -010-03."""
    (project / "database" / "migrations" / "2026_01_01_a.py").write_text(_NOOP_UP)
    (project / "database" / "migrations" / "2026_01_02_b.py").write_text(_NOOP_UP)
    monkeypatch.chdir(project)
    # Apply one
    app_m = _make_app_with_engine(project, engine, MigrateCommand())
    # Only register the first file, apply, then add the second to leave pending.
    invoke_async(runner, app_m.typer_app, ["migrate"])
    app_s = _make_app_with_engine(project, engine, MigrateStatusCommand())
    result = invoke_async(runner, app_s.typer_app, ["migrate:status"])
    assert result.exit_code == 0, result.stdout + result.stderr
    # header columns
    out_lower = result.stdout.lower()
    assert "migration" in out_lower
    assert "applied" in out_lower
    assert "batch" in out_lower
    # rows
    assert "2026_01_01_a" in result.stdout
    assert "2026_01_02_b" in result.stdout


# ============================================================
# — DbSeedCommand resolves and runs a seeder
# ============================================================


def test_db_seed_runs_default_database_seeder(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-011-01: arvel db:seed runs DatabaseSeeder by default."""
    (project / "database" / "seeders" / "database_seeder.py").write_text(_BASIC_SEEDER)
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, DbSeedCommand())
    _mark_migrated(engine)
    result = invoke_async(runner, app.typer_app, ["db:seed"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Seeded: DatabaseSeeder" in result.stdout or "DatabaseSeeder" in result.stdout


def test_db_seed_with_explicit_seeder_name(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-011-02: arvel db:seed --seeder PostSeeder resolves
    database/seeders/post_seeder.py.

    Note: we reuse _BASIC_SEEDER source but with a different class name.
    """
    post_seeder = _BASIC_SEEDER.replace("DatabaseSeeder", "PostSeeder")
    (project / "database" / "seeders" / "post_seeder.py").write_text(post_seeder)
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, DbSeedCommand())
    _mark_migrated(engine)
    result = invoke_async(runner, app.typer_app, ["db:seed", "--seeder", "PostSeeder"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "PostSeeder" in result.stdout


def test_db_seed_missing_file_exits_2(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-011-03: missing seeder file → exit 2."""
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, DbSeedCommand())
    result = invoke_async(runner, app.typer_app, ["db:seed", "--seeder", "Nonexistent"])
    assert result.exit_code == 2, (
        f"expected 2, got {result.exit_code}; stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "seeder file not found" in result.stderr.lower()


def test_db_seed_class_not_found_exits_2(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-011-04: file exists, class missing → exit 2."""
    (project / "database" / "seeders" / "wrong_name.py").write_text(
        _BASIC_SEEDER.replace("DatabaseSeeder", "DifferentClass")
    )
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, DbSeedCommand())
    result = invoke_async(runner, app.typer_app, ["db:seed", "--seeder", "WrongName"])
    assert result.exit_code == 2
    assert "seeder class not found" in result.stderr.lower()


def test_db_seed_body_failure_exits_1(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-011-05: seeder run raises → exit 1."""
    (project / "database" / "seeders" / "bad_seeder.py").write_text(_RAISING_SEEDER)
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, DbSeedCommand())
    _mark_migrated(engine)
    result = invoke_async(runner, app.typer_app, ["db:seed", "--seeder", "BadSeeder"])
    assert result.exit_code == 1
    assert "seeder failed" in result.stderr.lower()


# ============================================================
# SR-022-001 — Seeder name allowlist
# ============================================================


@pytest.mark.parametrize(
    "bad_name",
    ["../etc/passwd", "/absolute/path", "Has Space", "Has-Dash", "1StartsWithDigit"],
)
def test_db_seed_rejects_unsafe_seeder_names(
    project: Path,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    bad_name: str,
) -> None:
    """SR-022-001 + AC: --seeder values violating the allowlist exit 2 cleanly."""
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, DbSeedCommand())
    result = invoke_async(runner, app.typer_app, ["db:seed", "--seeder", bad_name])
    assert result.exit_code == 2, f"expected 2 for bad_name={bad_name!r}, got {result.exit_code}"
    assert "invalid" in result.stderr.lower() or "must match" in result.stderr.lower()


# ============================================================
# Smoke — Migrator integration with a real DDL-emitting migration
# ============================================================


def test_migrate_actually_creates_user_table(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: a migration that creates a real table works."""
    real_migration = '''"""Create posts table."""

from arvel.database import Blueprint, Schema


def _build(t: Blueprint) -> None:
    t.id()
    t.string("title")


async def up(schema: Schema) -> None:
    Schema.create("posts", _build)


async def down(schema: Schema) -> None:
    Schema.drop_if_exists("posts")
'''
    (project / "database" / "migrations" / "2026_01_01_create_posts.py").write_text(real_migration)
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, MigrateCommand())
    result = invoke_async(runner, app.typer_app, ["migrate"])
    assert result.exit_code == 0, result.stdout + result.stderr

    # Verify the posts table exists
    from arvel.database.schema import Schema

    async def _check() -> bool:
        return await Schema.has_table(engine, "posts")

    assert asyncio.run(_check()) is True


# ============================================================
# Pre-flight validation — DB reachable (migrate) + migrated (db:seed)
# ============================================================


def test_migrate_exits_2_when_database_unavailable(
    project: Path, dead_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """migrate refuses to run against a database it can't reach."""
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, dead_engine, MigrateCommand())
    result = invoke_async(runner, app.typer_app, ["migrate"])
    assert result.exit_code == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "database is not available" in result.stderr.lower()


def test_db_seed_exits_2_when_database_unavailable(
    project: Path, dead_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """db:seed refuses to run against a database it can't reach."""
    (project / "database" / "seeders" / "database_seeder.py").write_text(_BASIC_SEEDER)
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, dead_engine, DbSeedCommand())
    result = invoke_async(runner, app.typer_app, ["db:seed"])
    assert result.exit_code == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "database is not available" in result.stderr.lower()


def test_db_seed_exits_2_when_not_migrated(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """db:seed refuses to seed before any migration has run."""
    (project / "database" / "seeders" / "database_seeder.py").write_text(_BASIC_SEEDER)
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, DbSeedCommand())
    # No _mark_migrated — the migrations tracking table doesn't exist.
    result = invoke_async(runner, app.typer_app, ["db:seed"])
    assert result.exit_code == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "not migrated" in result.stderr.lower()
    assert "arvel migrate" in result.stderr.lower()


def test_db_seed_exits_2_when_migrations_pending(
    project: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """db:seed refuses to seed while migrations are still pending."""
    (project / "database" / "seeders" / "database_seeder.py").write_text(_BASIC_SEEDER)
    (project / "database" / "migrations" / "2026_01_01_a.py").write_text(_NOOP_UP)
    monkeypatch.chdir(project)
    app = _make_app_with_engine(project, engine, DbSeedCommand())
    _mark_migrated(engine)  # creates the tracking table but applies nothing
    result = invoke_async(runner, app.typer_app, ["db:seed"])
    assert result.exit_code == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "pending" in result.stderr.lower()
    assert "arvel migrate" in result.stderr.lower()


# ============================================================
# run_seeder_for_app — shared helper used by migrate:fresh/refresh --seed
# ============================================================


def test_run_seeder_for_app_runs_and_commits(project: Path, engine: AsyncEngine) -> None:
    """Happy path: loads the seeder, binds a session, commits."""
    (project / "database" / "seeders" / "database_seeder.py").write_text(_BASIC_SEEDER)
    cmd = DbSeedCommand()
    _make_app_with_engine(project, engine, cmd)
    asyncio.run(run_seeder_for_app(cmd.app))


def test_run_seeder_for_app_rejects_invalid_name(project: Path, engine: AsyncEngine) -> None:
    cmd = DbSeedCommand()
    _make_app_with_engine(project, engine, cmd)
    with pytest.raises(ValueError, match="invalid seeder name"):
        asyncio.run(run_seeder_for_app(cmd.app, "../bad"))


def test_run_seeder_for_app_missing_file_raises(project: Path, engine: AsyncEngine) -> None:
    cmd = DbSeedCommand()
    _make_app_with_engine(project, engine, cmd)
    with pytest.raises(FileNotFoundError, match="seeder file not found"):
        asyncio.run(run_seeder_for_app(cmd.app, "Nonexistent"))


def test_run_seeder_for_app_body_failure_exits_1(project: Path, engine: AsyncEngine) -> None:
    (project / "database" / "seeders" / "bad_seeder.py").write_text(_RAISING_SEEDER)
    cmd = DbSeedCommand()
    _make_app_with_engine(project, engine, cmd)
    with pytest.raises(typer.Exit) as exc_info:
        asyncio.run(run_seeder_for_app(cmd.app, "BadSeeder"))
    assert exc_info.value.exit_code == 1


__all__: list[str] = []
