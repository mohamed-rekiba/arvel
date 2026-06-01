"""Unit tests for arvel.database.migrator.Migrator.

Red-state tests: they fail on import until the migrator module ships."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio

# --- These imports will fail until execution ships --------------------
from arvel.database.migrator import (
    MigrationFailedError,
    MigrationFileInvalidError,
    MigrationStatus,
    Migrator,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_BASIC_UP = '''"""Test migration."""

from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    Schema.create("posts", lambda t: Blueprint(table_name="posts"))


async def down(schema: Schema) -> None:
    Schema.drop_if_exists("posts")
'''


_RAISING_UP = '''"""Bad migration."""

from arvel.database import Schema


async def up(schema: Schema) -> None:
    raise RuntimeError("oops in up")


async def down(schema: Schema) -> None:
    return
'''


_NOOP_UP = '''"""No-op migration."""

from arvel.database import Schema


async def up(schema: Schema) -> None:
    return


async def down(schema: Schema) -> None:
    return
'''


_MISSING_UP = '''"""Invalid migration — no up()."""

async def down(schema: Schema) -> None:
    return
'''


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    """Fresh in-memory SQLite engine for each test."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
def migrations_dir(tmp_path: Path) -> Path:
    """Empty migrations directory."""
    d = tmp_path / "database" / "migrations"
    d.mkdir(parents=True)
    return d


def _write_migration(migrations_dir: Path, name: str, body: str) -> Path:
    p = migrations_dir / f"{name}.py"
    p.write_text(body)
    return p


# ============================================================
# -001 — Migrator orchestrator module
# ============================================================


def test_migrator_instantiates_without_db_touch(engine: AsyncEngine, migrations_dir: Path) -> None:
    """construction does not touch the database."""
    Migrator(engine, migrations_dir)


def test_migration_status_is_frozen_dataclass() -> None:
    """MigrationStatus has the required fields and is frozen."""
    from dataclasses import FrozenInstanceError, fields, is_dataclass

    s = MigrationStatus(name="foo", applied=False, batch=None, applied_at=None)
    assert s.name == "foo"
    assert s.applied is False
    assert s.batch is None
    assert s.applied_at is None

    assert is_dataclass(MigrationStatus)
    field_names = {f.name for f in fields(MigrationStatus)}
    assert field_names == {"name", "applied", "batch", "applied_at"}

    # Frozen dataclasses raise FrozenInstanceError on attribute assignment.
    # Use type-erased setattr to keep mypy out of it.
    setter: Callable[[object, str, object], None] = setattr
    with pytest.raises(FrozenInstanceError):
        setter(s, "applied", True)


# ============================================================
# -002 — Tracking table created on first run
# ============================================================


@pytest.mark.asyncio
async def test_ensure_table_creates_migrations_table(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """After ensure_table, the `migrations` table exists."""
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    from arvel.database.schema import Schema

    exists = await Schema.has_table(engine, "migrations")
    assert exists is True


@pytest.mark.asyncio
async def test_ensure_table_is_idempotent(engine: AsyncEngine, migrations_dir: Path) -> None:
    """second ensure_table call does not raise."""
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    await migrator.ensure_table()


# ============================================================
# -003 — applied returns ordered list of names
# ============================================================


@pytest.mark.asyncio
async def test_applied_empty_table_returns_empty_list(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """3-01."""
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    assert await migrator.applied() == []


@pytest.mark.asyncio
async def test_applied_returns_stems_in_insertion_order(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """3-02 + 3-03."""
    _write_migration(migrations_dir, "2026_01_01_000001_first", _NOOP_UP)
    _write_migration(migrations_dir, "2026_01_01_000002_second", _NOOP_UP)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    await migrator.upgrade()
    names = await migrator.applied()
    assert names == ["2026_01_01_000001_first", "2026_01_01_000002_second"]


# ============================================================
# -004 — pending returns files not yet applied
# ============================================================


@pytest.mark.asyncio
async def test_pending_returns_unapplied_files(engine: AsyncEngine, migrations_dir: Path) -> None:
    """4-01."""
    _write_migration(migrations_dir, "2026_01_01_000001_a", _NOOP_UP)
    _write_migration(migrations_dir, "2026_01_01_000002_b", _NOOP_UP)
    _write_migration(migrations_dir, "2026_01_01_000003_c", _NOOP_UP)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    # Apply only the first
    pending_before = await migrator.pending()
    assert [p.stem for p in pending_before] == [
        "2026_01_01_000001_a",
        "2026_01_01_000002_b",
        "2026_01_01_000003_c",
    ]


@pytest.mark.asyncio
async def test_pending_skips_underscore_prefixed_files(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """`__init__.py` and friends are not picked up."""
    _write_migration(migrations_dir, "__init__", "")
    _write_migration(migrations_dir, "_helper", "")
    _write_migration(migrations_dir, "2026_01_01_real_migration", _NOOP_UP)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    names = [p.stem for p in await migrator.pending()]
    assert names == ["2026_01_01_real_migration"]


@pytest.mark.asyncio
async def test_pending_does_not_import_modules(engine: AsyncEngine, migrations_dir: Path) -> None:
    """pending is non-destructive — even a syntactically
    invalid file is listed without raising."""
    _write_migration(migrations_dir, "2026_01_01_syntax_error", "this is not valid python")
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    names = [p.stem for p in await migrator.pending()]
    assert "2026_01_01_syntax_error" in names


# ============================================================
# -005 — upgrade runs migrations in transactions
# ============================================================


@pytest.mark.asyncio
async def test_upgrade_dry_run_returns_names_without_inserting(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """dry_run=True returns names but does not write."""
    _write_migration(migrations_dir, "2026_01_01_a", _NOOP_UP)
    _write_migration(migrations_dir, "2026_01_01_b", _NOOP_UP)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    names = await migrator.upgrade(dry_run=True)
    assert names == ["2026_01_01_a", "2026_01_01_b"]
    # nothing should be applied
    assert await migrator.applied() == []


@pytest.mark.asyncio
async def test_upgrade_assigns_same_batch_to_one_invocation(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """5-01 + 5-05: all migrations in one upgrade
    share the same batch number."""
    _write_migration(migrations_dir, "2026_01_01_a", _NOOP_UP)
    _write_migration(migrations_dir, "2026_01_01_b", _NOOP_UP)
    _write_migration(migrations_dir, "2026_01_01_c", _NOOP_UP)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    names = await migrator.upgrade()
    assert names == ["2026_01_01_a", "2026_01_01_b", "2026_01_01_c"]
    statuses = await migrator.status()
    batches = {s.batch for s in statuses if s.applied}
    assert batches == {1}


@pytest.mark.asyncio
async def test_upgrade_subsequent_calls_increment_batch(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """5-05 (delta across calls)."""
    _write_migration(migrations_dir, "2026_01_01_a", _NOOP_UP)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    await migrator.upgrade()
    _write_migration(migrations_dir, "2026_01_02_b", _NOOP_UP)
    await migrator.upgrade()
    statuses_by_name = {s.name: s for s in await migrator.status()}
    assert statuses_by_name["2026_01_01_a"].batch == 1
    assert statuses_by_name["2026_01_02_b"].batch == 2


@pytest.mark.asyncio
async def test_upgrade_with_nothing_pending_returns_empty(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """5-06."""
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    assert await migrator.upgrade() == []


@pytest.mark.asyncio
async def test_upgrade_stops_at_failure_keeps_earlier_applied(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """5-02 + 5-03: per-migration transactions; failure
    leaves earlier applied; raises MigrationFailedError with the name."""
    _write_migration(migrations_dir, "2026_01_01_a", _NOOP_UP)
    _write_migration(migrations_dir, "2026_01_01_b", _RAISING_UP)
    _write_migration(migrations_dir, "2026_01_01_c", _NOOP_UP)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    with pytest.raises(MigrationFailedError) as exc:
        await migrator.upgrade()
    assert "2026_01_01_b" in str(exc.value)
    # First one stays applied, second and third do not.
    applied = await migrator.applied()
    assert applied == ["2026_01_01_a"]


# ============================================================
# -006 — rollback undoes the last batch
# ============================================================


@pytest.mark.asyncio
async def test_rollback_with_nothing_applied_returns_empty(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """6-03."""
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    assert await migrator.rollback() == []


@pytest.mark.asyncio
async def test_rollback_undoes_only_last_batch(engine: AsyncEngine, migrations_dir: Path) -> None:
    """6-01 + 6-04: batch 2 (size 2) is undone; batch 1
    (size 3) stays."""
    for name in ("2026_01_01_a", "2026_01_01_b", "2026_01_01_c"):
        _write_migration(migrations_dir, name, _NOOP_UP)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    await migrator.upgrade()  # batch 1
    for name in ("2026_01_02_d", "2026_01_02_e"):
        _write_migration(migrations_dir, name, _NOOP_UP)
    await migrator.upgrade()  # batch 2
    rolled = await migrator.rollback()
    assert set(rolled) == {"2026_01_02_d", "2026_01_02_e"}
    # reverse order — last applied is first rolled back
    assert rolled == ["2026_01_02_e", "2026_01_02_d"]
    remaining = await migrator.applied()
    assert remaining == ["2026_01_01_a", "2026_01_01_b", "2026_01_01_c"]


# ============================================================
# -007 — status reflects current state
# ============================================================


@pytest.mark.asyncio
async def test_status_returns_row_per_file(engine: AsyncEngine, migrations_dir: Path) -> None:
    """7-01 + 7-04."""
    _write_migration(migrations_dir, "2026_01_01_a", _NOOP_UP)
    _write_migration(migrations_dir, "2026_01_02_b", _NOOP_UP)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    statuses = await migrator.status()
    assert [s.name for s in statuses] == ["2026_01_01_a", "2026_01_02_b"]
    assert all(not s.applied for s in statuses)
    assert all(s.batch is None for s in statuses)
    assert all(s.applied_at is None for s in statuses)


@pytest.mark.asyncio
async def test_status_marks_applied_with_batch_and_timestamp(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """7-02 + 7-03."""
    _write_migration(migrations_dir, "2026_01_01_a", _NOOP_UP)
    _write_migration(migrations_dir, "2026_01_02_b", _NOOP_UP)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    await migrator.upgrade()
    statuses_by_name = {s.name: s for s in await migrator.status()}
    a = statuses_by_name["2026_01_01_a"]
    b = statuses_by_name["2026_01_02_b"]
    assert a.applied is True and a.batch == 1
    assert b.applied is True and b.batch == 1
    assert isinstance(a.applied_at, datetime)
    # Reasonable timestamp — within the last minute.
    delta = abs((datetime.now(UTC) - a.applied_at.replace(tzinfo=UTC)).total_seconds())
    assert delta < 60


@pytest.mark.asyncio
async def test_status_does_not_import_user_modules(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """even a syntactically broken file is listed without
    raising. (Same property as test_pending_does_not_import_modules but for
    status)."""
    _write_migration(migrations_dir, "2026_01_01_syntax_error", "this is not valid python")
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    statuses = await migrator.status()
    assert any(s.name == "2026_01_01_syntax_error" for s in statuses)


# ============================================================
# -012 — Migration file shape validation
# ============================================================


@pytest.mark.asyncio
async def test_upgrade_rejects_file_without_up(engine: AsyncEngine, migrations_dir: Path) -> None:
    """missing `up` callable → MigrationFileInvalidError with name."""
    _write_migration(migrations_dir, "2026_01_01_bad", _MISSING_UP)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    with pytest.raises(MigrationFileInvalidError) as exc:
        await migrator.upgrade()
    assert "2026_01_01_bad" in str(exc.value)


# ============================================================
# Edge cases — defensive branches and bridge semantics
# ============================================================


@pytest.mark.asyncio
async def test_discover_returns_empty_when_migrations_dir_missing(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """Migrator pointed at a non-existent dir returns empty file list."""
    missing = tmp_path / "does-not-exist"
    migrator = Migrator(engine, missing)
    await migrator.ensure_table()
    assert await migrator.applied() == []
    assert await migrator.pending() == []
    assert await migrator.upgrade() == []


_MISSING_DOWN = '''"""Migration with up but no down."""

from arvel.database import Schema


async def up(schema: Schema) -> None:
    return
'''


@pytest.mark.asyncio
async def test_rollback_rejects_file_without_down(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """A migration applied without `down` cannot be rolled back."""
    _write_migration(migrations_dir, "2026_01_01_no_down", _MISSING_DOWN)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    await migrator.upgrade()
    with pytest.raises(MigrationFileInvalidError) as exc:
        await migrator.rollback()
    assert "2026_01_01_no_down" in str(exc.value)


_IMPORT_ERROR_BODY = '''"""Migration that fails at import time."""

raise RuntimeError("import-time boom")


async def up(schema: Schema) -> None:
    return


async def down(schema: Schema) -> None:
    return
'''


@pytest.mark.asyncio
async def test_upgrade_re_raises_with_cleanup_on_import_failure(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """A migration file that raises at import time → propagates wrapped failure
    and doesn't leak partial modules in sys.modules."""
    import sys

    _write_migration(migrations_dir, "2026_01_01_imp_err", _IMPORT_ERROR_BODY)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()

    pre_keys = set(sys.modules.keys())
    with pytest.raises((MigrationFailedError, RuntimeError)):
        await migrator.upgrade()
    leaked = [k for k in sys.modules if k.startswith("_arvel_migration_") and k not in pre_keys]
    assert leaked == []


_SYNC_DEF_UP = '''"""Migration written with sync `def up` (return None directly)."""

from arvel.database import Schema


def up(schema: Schema) -> None:
    return


def down(schema: Schema) -> None:
    return
'''


@pytest.mark.asyncio
async def test_upgrade_accepts_sync_def_migration(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """`def up(schema)` (not `async def`) is fine — the bridge handles
    non-coroutine return values."""
    _write_migration(migrations_dir, "2026_01_01_sync_def", _SYNC_DEF_UP)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    applied = await migrator.upgrade()
    assert applied == ["2026_01_01_sync_def"]


_REAL_AWAIT_UP = '''"""Migration that actually awaits — not supported."""

import asyncio
from arvel.database import Schema


async def up(schema: Schema) -> None:
    await asyncio.sleep(0)


async def down(schema: Schema) -> None:
    return
'''


@pytest.mark.asyncio
async def test_upgrade_rejects_real_await_in_migration(
    engine: AsyncEngine, migrations_dir: Path
) -> None:
    """`await` inside up/down bodies is not supported and surfaces as
    a MigrationFailedError wrapping a RuntimeError."""
    _write_migration(migrations_dir, "2026_01_01_real_await", _REAL_AWAIT_UP)
    migrator = Migrator(engine, migrations_dir)
    await migrator.ensure_table()
    with pytest.raises(MigrationFailedError) as exc_info:
        await migrator.upgrade()
    assert "2026_01_01_real_await" in str(exc_info.value)
    assert isinstance(exc_info.value.original, RuntimeError)
    assert "suspended on an `await`" in str(exc_info.value.original)


__all__: list[str] = []
