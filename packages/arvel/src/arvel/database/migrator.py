"""Migration runner.

The :class:`Migrator` orchestrates user migration files against a
Laravel-style ``migrations`` tracking table. It honors the existing
async-function-based file contract that ``arvel make:migration`` generates:.. code-block:: python

 from arvel.database import Schema

 async def up(schema: Schema) -> None:...
 async def down(schema: Schema) -> None:...

Inside a user ``up``/``down`` body, ``Schema.create(...)`` and friends emit
DDL via Alembic's ``op`` proxy. The Migrator binds that proxy to a real
SQLAlchemy connection per migration so each one runs in its own transaction
— a body failure leaves earlier migrations applied (Laravel semantics).

Implementation note: the orchestration stays on the ``AsyncEngine`` path,
using ``conn.run_sync`` to obtain a sync ``Connection`` for Alembic's
``MigrationContext``. Inside the sync callback the user's ``async def up``
is driven manually one step at a time — typical migration bodies never
``await`` anything (``Schema.create`` and friends are sync), so the coroutine
runs to ``StopIteration`` on the first ``send(None)``. If a body does
suspend (which would indicate a misuse), we raise a clear error rather than
deadlock waiting on a nonexistent event loop.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    delete,
    func,
    insert,
    select,
    text,
)
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncEngine

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection as SyncConnection


__all__ = [
    "MigrationFailedError",
    "MigrationFileInvalidError",
    "MigrationStatus",
    "Migrator",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MigrationFileInvalidError(Exception):
    """A migration file is missing required ``up()`` or ``down()`` callables."""

    def __init__(self, name: str, missing: str) -> None:
        super().__init__(f"Migration {name!r} is invalid: no module-level async {missing!r}.")
        self.name = name
        self.missing = missing


class MigrationFailedError(Exception):
    """A migration body raised during ``upgrade()`` or ``rollback()``."""

    def __init__(self, name: str, original: BaseException) -> None:
        super().__init__(f"Migration {name!r} failed: {original!r}")
        self.name = name
        self.original = original


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MigrationStatus:
    """One row in ``arvel migrate:status`` output."""

    name: str
    applied: bool
    batch: int | None
    applied_at: datetime | None


# ---------------------------------------------------------------------------
# Schema-table description
# ---------------------------------------------------------------------------

_MIGRATIONS_TABLE_LOCK_ID = 882917379


def _build_migrations_table() -> Table:
    """Return the SQLAlchemy ``Table`` describing the tracking table.

    Uses a fresh ``MetaData`` so the table is not registered against any
    global ``DeclarativeBase``. Each ``Migrator`` instance gets its own
    metadata so tests that drop and recreate engines don't collide.
    """
    metadata = MetaData()
    return Table(
        "migrations",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("migration", String(255), nullable=False, unique=True),
        Column("batch", Integer, nullable=False),
        Column(
            "applied_at",
            DateTime(timezone=False),
            nullable=False,
            server_default=func.current_timestamp(),
        ),
    )


# ---------------------------------------------------------------------------
# Migrator
# ---------------------------------------------------------------------------


class Migrator:
    """Laravel-style migration orchestrator.

    Parameters
    ----------
    engine:
        SQLAlchemy ``AsyncEngine`` to run migrations against.
    migrations_path:
        Filesystem directory containing the user's migration files
        (one ``.py`` per migration, sorted lexicographically).
    """

    def __init__(self, engine: AsyncEngine, migrations_path: Path) -> None:
        self._engine = engine
        self._migrations_path = migrations_path
        self._table = _build_migrations_table()

    # ---- public API -----------------------------------------------------

    async def ensure_table(self) -> None:
        """Create the ``migrations`` table if it does not exist. Idempotent."""
        async with self._engine.begin() as conn:
            await conn.run_sync(self._ensure_table_in_conn)

    async def applied(self) -> list[str]:
        """Return applied migration name-stems in application order."""
        async with self._engine.connect() as conn:
            return await conn.run_sync(self._applied_in_conn)

    async def pending(self) -> list[Path]:
        """Return migration files not yet applied, lexicographic order."""
        applied_set = set(await self.applied())
        return [p for p in self._discover_files() if p.stem not in applied_set]

    async def upgrade(self, *, dry_run: bool = False) -> list[str]:
        """Apply every pending migration in order. Returns applied name-stems."""
        pending = await self.pending()
        if dry_run:
            return [p.stem for p in pending]
        if not pending:
            return []

        batch = await self._next_batch_number()
        applied: list[str] = []
        for path in pending:
            await self._apply_one(path, batch)
            applied.append(path.stem)
        return applied

    async def rollback(self) -> list[str]:
        """Undo the migrations in the most recent batch. Returns rolled names."""
        async with self._engine.connect() as conn:
            names_to_rollback = await conn.run_sync(self._rollback_targets_in_conn)
        if not names_to_rollback:
            return []

        rolled: list[str] = []
        for name in names_to_rollback:
            path = self._path_for_name(name)
            await self._roll_back_one(path, name)
            rolled.append(name)
        return rolled

    async def drop_all(self) -> list[str]:
        """Drop every table in the database (including the migrations tracking table).

        Order of operations keeps PostgreSQL happy:
        1. Materialized views — they hold references to base tables and block DROP TABLE.
        2. Tables — with CASCADE so any residual regular-view dependencies are cleaned up.
        3. User-defined ENUM types — PostgreSQL doesn't drop these with the table; they
           must be swept separately or the next migrate:fresh / migrate:refresh would
           fail with DuplicateObjectError when the table's up() re-creates them.

        Returns the names of dropped tables in the order they were dropped.
        Used by ``migrate:fresh``.
        """
        dropped: list[str] = []

        # Step 1: materialized views (block base-table drops via pg dependencies).
        async with self._engine.begin() as conn:
            mat_views = await conn.run_sync(self._list_materialized_views_in_conn)
        for view_name in mat_views:
            async with self._engine.begin() as conn:
                await conn.run_sync(self._drop_materialized_view_in_conn, view_name)

        # Step 2: tables — CASCADE handles any remaining view-level dependencies.
        async with self._engine.begin() as conn:
            names = await conn.run_sync(self._list_tables_in_conn)
        if not names and not mat_views:
            return []
        remaining = list(names)
        for _ in range(3):
            if not remaining:
                break
            still: list[str] = []
            for name in remaining:
                try:
                    async with self._engine.begin() as conn:
                        await conn.run_sync(self._drop_table_in_conn, name)
                    dropped.append(name)
                except Exception:  # noqa: BLE001 — retry on next pass
                    still.append(name)
            remaining = still
        if remaining:
            joined = ", ".join(remaining)
            msg = f"Could not drop tables after 3 passes: {joined}"
            raise RuntimeError(msg)

        # Step 3: user-defined ENUM types (PostgreSQL only; survive table drops).
        async with self._engine.begin() as conn:
            await conn.run_sync(self._drop_enum_types_in_conn)

        return dropped

    async def reset(self) -> list[str]:
        """Roll back every applied migration in reverse order.

        Walks ``applied()``, then runs each migration's ``down(schema)`` in its
        own transaction and deletes the corresponding tracking row.

        If any ``down()`` body raises, exits the loop and re-raises (the caller
        maps it to exit 1). Subsequent ``reset()`` calls pick up where the
        failure left off.
        """
        applied_names = await self.applied()
        if not applied_names:
            return []
        rolled: list[str] = []
        for name in reversed(applied_names):
            path = self._path_for_name(name)
            await self._roll_back_one(path, name)
            rolled.append(name)
        return rolled

    async def status(self) -> list[MigrationStatus]:
        """Return one ``MigrationStatus`` per discovered file."""
        files = self._discover_files()
        async with self._engine.connect() as conn:
            applied_rows: dict[str, tuple[int, datetime]] = await conn.run_sync(
                self._applied_rows_in_conn
            )

        return [
            MigrationStatus(
                name=path.stem,
                applied=path.stem in applied_rows,
                batch=applied_rows[path.stem][0] if path.stem in applied_rows else None,
                applied_at=(applied_rows[path.stem][1] if path.stem in applied_rows else None),
            )
            for path in files
        ]

    # ---- sync callbacks (run inside conn.run_sync) ----------------------

    def _ensure_table_in_conn(self, sync_conn: SyncConnection) -> None:
        if sync_conn.dialect.name == "postgresql":
            sync_conn.exec_driver_sql(f"SELECT pg_advisory_xact_lock({_MIGRATIONS_TABLE_LOCK_ID})")
        self._table.create(sync_conn, checkfirst=True)

    def _list_tables_in_conn(self, sync_conn: SyncConnection) -> list[str]:
        return list(sa_inspect(sync_conn).get_table_names())

    def _list_materialized_views_in_conn(self, sync_conn: SyncConnection) -> list[str]:
        from arvel.database.schema import materialized_view_names

        return materialized_view_names(sa_inspect(sync_conn))

    def _drop_table_in_conn(self, sync_conn: SyncConnection, name: str) -> None:
        if sync_conn.dialect.name == "postgresql":
            # CASCADE drops any dependent views not caught by the mat-view sweep.
            sync_conn.execute(text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))
        else:
            metadata = MetaData()
            table = Table(name, metadata, autoload_with=sync_conn)
            table.drop(sync_conn, checkfirst=True)

    def _drop_materialized_view_in_conn(self, sync_conn: SyncConnection, name: str) -> None:
        sync_conn.execute(text(f'DROP MATERIALIZED VIEW IF EXISTS "{name}"'))

    def _drop_enum_types_in_conn(self, sync_conn: SyncConnection) -> None:
        if sync_conn.dialect.name != "postgresql":
            return
        rows = sync_conn.execute(
            text(
                "SELECT typname FROM pg_type "
                "JOIN pg_namespace ON pg_namespace.oid = pg_type.typnamespace "
                "WHERE typtype = 'e' AND nspname = 'public'"
            )
        ).fetchall()
        for row in rows:
            sync_conn.execute(text(f'DROP TYPE IF EXISTS "{row[0]}"'))

    def _applied_in_conn(self, sync_conn: SyncConnection) -> list[str]:
        result = sync_conn.execute(select(self._table.c.migration).order_by(self._table.c.id))
        return [row[0] for row in result.fetchall()]

    def _rollback_targets_in_conn(self, sync_conn: SyncConnection) -> list[str]:
        max_batch = sync_conn.execute(select(func.max(self._table.c.batch))).scalar()
        if max_batch is None:
            return []
        rows = sync_conn.execute(
            select(self._table.c.migration)
            .where(self._table.c.batch == max_batch)
            .order_by(self._table.c.id.desc())
        ).fetchall()
        return [row[0] for row in rows]

    def _applied_rows_in_conn(self, sync_conn: SyncConnection) -> dict[str, tuple[int, datetime]]:
        return {
            row[0]: (row[1], row[2])
            for row in sync_conn.execute(
                select(
                    self._table.c.migration,
                    self._table.c.batch,
                    self._table.c.applied_at,
                )
            ).fetchall()
        }

    async def _next_batch_number(self) -> int:
        async with self._engine.connect() as conn:
            current = await conn.run_sync(self._read_max_batch_in_conn)
        return (current or 0) + 1

    def _read_max_batch_in_conn(self, sync_conn: SyncConnection) -> int | None:
        return sync_conn.execute(select(func.max(self._table.c.batch))).scalar()

    # ---- per-migration apply / rollback ---------------------------------

    async def _apply_one(self, path: Path, batch: int) -> None:
        """Run a single migration's ``up`` and insert its tracking row."""
        module = _load_migration_module(path)
        if not hasattr(module, "up"):
            raise MigrationFileInvalidError(path.stem, "up")
        up_callable = cast("Any", module).up
        name = path.stem
        table = self._table

        def _run_up(sync_conn: SyncConnection) -> None:
            _run_user_migration_callable(sync_conn, up_callable)

        def _record(sync_conn: SyncConnection) -> None:
            sync_conn.execute(insert(table).values(migration=name, batch=batch))

        async with self._engine.begin() as conn:
            try:
                await conn.run_sync(_run_up)
                await conn.run_sync(_record)
            except MigrationFileInvalidError:
                raise
            except Exception as exc:
                raise MigrationFailedError(name, exc) from exc

    async def _roll_back_one(self, path: Path, name: str) -> None:
        """Run a single migration's ``down`` and delete its tracking row."""
        module = _load_migration_module(path)
        if not hasattr(module, "down"):
            raise MigrationFileInvalidError(name, "down")
        down_callable = cast("Any", module).down
        table = self._table

        def _run_down(sync_conn: SyncConnection) -> None:
            _run_user_migration_callable(sync_conn, down_callable)

        def _untrack(sync_conn: SyncConnection) -> None:
            sync_conn.execute(delete(table).where(table.c.migration == name))

        async with self._engine.begin() as conn:
            try:
                await conn.run_sync(_run_down)
                await conn.run_sync(_untrack)
            except MigrationFileInvalidError:
                raise
            except Exception as exc:
                raise MigrationFailedError(name, exc) from exc

    # ---- discovery -------------------------------------------------------

    def _discover_files(self) -> list[Path]:
        """Return ``.py`` files (no underscore prefix) in lexicographic order."""
        if not self._migrations_path.exists():
            return []
        return sorted(p for p in self._migrations_path.glob("*.py") if not p.name.startswith("_"))

    def _path_for_name(self, name: str) -> Path:
        return self._migrations_path / f"{name}.py"


# ---------------------------------------------------------------------------
# Module loading + sync/async bridge
# ---------------------------------------------------------------------------


def _load_migration_module(path: Path) -> ModuleType:
    """Import a migration file as a unique module.

    Uses ``spec_from_file_location`` with a per-file unique module name so
    repeated imports within the same Python process (notably in tests) do not
    cache-poison ``sys.modules``. The module name uses ``id(path)`` for
    additional uniqueness across path-instance recreations.
    """
    module_name = f"_arvel_migration_{path.stem}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise MigrationFileInvalidError(path.stem, "loader")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _run_user_migration_callable(sync_conn: SyncConnection, callable_: Any) -> None:
    """Bridge: run a user migration body against ``sync_conn``.

    Configures Alembic's ``MigrationContext`` + ``Operations`` so that calls
    to ``Schema.create(...)`` inside the user's body emit DDL through this
    connection, then invokes ``callable_(Schema)``.

    Migration files are generated as ``async def up(schema)`` / ``down(schema)``
    for forward-compatibility, but their bodies only call synchronous
    ``Schema.*`` operations. We drive the resulting coroutine by hand: a single
    ``send(None)`` step completes it (``StopIteration``) when the body never
    actually suspends. If the body *does* suspend on a real ``await``, we
    surface a clear error rather than silently dropping the work or trying to
    start a nested event loop.
    """
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    from arvel.database import Schema

    ctx = MigrationContext.configure(connection=sync_conn)
    with Operations.context(ctx):
        result = callable_(Schema)
        if inspect.iscoroutine(result):
            try:
                result.send(None)
            except StopIteration:
                return
            # Body actually suspended on a real await — not supported here.
            result.close()
            raise RuntimeError(
                "Migration body suspended on an `await`. "
                "Migration up()/down() must only call synchronous Schema "
                "operations; real I/O inside a migration is not supported."
            )
