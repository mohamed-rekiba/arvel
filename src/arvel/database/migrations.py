"""arvel.database.migrations — Laravel-style migrations driven by **Alembic**.

A ``Migration`` declares ``up(schema)``/``down(schema)``; ``Schema`` is a thin facade
over an Alembic ``Operations`` object (``create``/``drop``/views/extensions), so schema
changes go through Alembic (autogenerate/branching/history) rather than raw-SQL DDL — a
raw migrator is a spec violation (doc 08). ``Migrator`` applies migrations on the write
connection via ``run_sync`` (Alembic is sync). Alembic is lazy-imported.
Grounded in knowledge/port/08-advanced-database.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.database.schema import (
    PLAIN_IDENTIFIER,
    Blueprint,
    create_extension,
    create_materialized_view,
    create_view,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from arvel.database.connections import ConnectionResolver


def _index_columns(columns: Sequence[str]) -> list[Any]:
    """A plain column name stays a string; anything else (an expression like ``name->>'en'``) is
    wrapped in ``sa.text`` so it's emitted as an expression index, not a quoted column name."""
    import sqlalchemy as sa

    return [c if PLAIN_IDENTIFIER.match(c) else sa.text(f"({c})") for c in columns]


def _warn_pg_only(feature: str, dialect: str, *, action: str) -> None:
    """Surface (not silently swallow) a Postgres-only DDL feature used on another dialect."""
    from arvel.kernel.logging import LogManager

    LogManager().channel("database").warning(
        "postgres_only_feature", feature=feature, dialect=dialect, action=action
    )


class Schema:
    """Operations facade bound to an Alembic ``Operations`` instance.

    Several DDL features are **Postgres-only** (materialized views, ``CREATE EXTENSION``, GIN/GiST
    access methods). Rather than silently degrade or crash on another dialect, these emit a
    ``postgres_only_feature`` warning and degrade sensibly (MV → plain view, extension → skip,
    GIN/GiST → plain index) so a sqlite/mysql test run is honest about what it did.
    """

    def __init__(self, op: Any) -> None:
        self._op = op

    @property
    def dialect(self) -> str:
        """The active connection's dialect name (``postgresql`` / ``sqlite`` / ``mysql``)."""
        return str(self._op.get_bind().dialect.name)

    def create(self, name: str, define: Callable[[Blueprint], Any]) -> None:
        blueprint = Blueprint(name)
        define(blueprint)
        self._op.create_table(name, *blueprint.core_columns())
        for spec in blueprint.index_specs():  # btree/GIN/GiST → a separate create_index op
            if spec["using"] in ("gin", "gist") and self.dialect != "postgresql":
                _warn_pg_only(f"{spec['using'].upper()} index", self.dialect, action="plain index")
            self._op.create_index(
                spec["name"], name, _index_columns(spec["columns"]), postgresql_using=spec["using"]
            )

    def drop(self, name: str) -> None:
        self._op.drop_table(name)

    def execute(self, statement: Any) -> None:
        self._op.execute(statement)

    def create_view(self, name: str, selectable: Any) -> None:
        self._op.execute(create_view(name, selectable))

    def create_materialized_view(self, name: str, selectable: Any) -> None:
        """A Postgres materialized view. On a dialect without them (sqlite/mysql) this warns and
        creates a **plain view** instead, so the same migration runs everywhere (the view is live, not
        materialized — call ``REFRESH MATERIALIZED VIEW`` only on Postgres)."""
        if self.dialect != "postgresql":
            _warn_pg_only("materialized view", self.dialect, action="plain view")
            self._op.execute(create_view(name, selectable))
            return
        self._op.execute(create_materialized_view(name, selectable))

    def create_extension(self, name: str) -> None:
        """``CREATE EXTENSION`` (Postgres). A no-op (with a warning) on other dialects."""
        if self.dialect != "postgresql":
            _warn_pg_only(f"extension {name!r}", self.dialect, action="skipped")
            return
        self._op.execute(create_extension(name))


class Migration:
    """Base migration: subclass and implement ``up`` and ``down``."""

    _name: str = ""  # set to the file stem by discover_migrations; else the class name is used

    @property
    def name(self) -> str:
        """The stable identifier recorded in the migrations table — the file stem when discovered
        from ``database/migrations`` (set by :func:`discover_migrations`), else the class name."""
        return self._name or type(self).__name__

    def up(self, schema: Schema) -> None:
        raise NotImplementedError

    def down(self, schema: Schema) -> None:
        raise NotImplementedError


_MIGRATIONS_TABLE = "arvel_migrations"


class Migrator:
    """Runs migrations through Alembic on the write connection, recording applied migrations in the
    ``arvel_migrations`` table so ``migrate`` is **idempotent** (only pending migrations run) and
    ``migrate:rollback`` reverts the last batch (Laravel parity)."""

    def __init__(self, resolver: ConnectionResolver, name: str | None = None) -> None:
        self._resolver = resolver
        self._name = name

    async def run(self, migrations: Sequence[Migration]) -> int:
        """Apply every not-yet-applied migration (in order) as one new batch. Returns how many ran."""
        async with self._resolver.engine(self._name).begin() as conn:
            return int(await conn.run_sync(self._apply, list(migrations), "up"))

    async def rollback(self, migrations: Sequence[Migration]) -> int:
        """Roll back the migrations in the most recent batch (reverse order). Returns how many ran."""
        async with self._resolver.engine(self._name).begin() as conn:
            return int(await conn.run_sync(self._apply, list(migrations), "down"))

    async def drop_all(self) -> int:
        """Reflect and drop every table on the connection (DB-agnostic — Postgres/sqlite). Backs
        ``db:wipe`` and ``migrate:fresh``. Returns the number of tables dropped."""
        from sqlalchemy import MetaData

        meta = MetaData()
        async with self._resolver.engine(self._name).begin() as conn:
            await conn.run_sync(meta.reflect)
            await conn.run_sync(meta.drop_all)
        return len(meta.tables)

    @staticmethod
    def _apply(sync_conn: Any, migrations: list[Migration], direction: str) -> int:
        import sqlalchemy as sa
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        sync_conn.execute(
            sa.text(
                f"CREATE TABLE IF NOT EXISTS {_MIGRATIONS_TABLE} "
                "(name VARCHAR(255) PRIMARY KEY, batch INTEGER NOT NULL)"
            )
        )
        applied: set[str] = set(
            sync_conn.execute(sa.text(f"SELECT name FROM {_MIGRATIONS_TABLE}")).scalars()  # noqa: S608 # nosec B608 - trusted constant table name; values bound
        )
        context = MigrationContext.configure(sync_conn)
        schema = Schema(Operations(context))

        if direction == "up":
            pending = [m for m in migrations if m.name not in applied]
            if not pending:
                return 0
            next_batch = (
                sync_conn.execute(
                    sa.text(f"SELECT COALESCE(MAX(batch), 0) FROM {_MIGRATIONS_TABLE}")  # noqa: S608 # nosec B608 - trusted constant table name; values bound
                ).scalar()
                or 0
            ) + 1
            for migration in pending:
                migration.up(schema)
                sync_conn.execute(
                    sa.text(f"INSERT INTO {_MIGRATIONS_TABLE} (name, batch) VALUES (:n, :b)"),  # noqa: S608 # nosec B608 - trusted constant table name; values bound
                    {"n": migration.name, "b": next_batch},
                )
            return len(pending)

        # down: revert only the most recent batch, in reverse order
        last_batch = sync_conn.execute(
            sa.text(f"SELECT MAX(batch) FROM {_MIGRATIONS_TABLE}")  # noqa: S608 # nosec B608 - trusted constant table name; values bound
        ).scalar()
        if last_batch is None:
            return 0
        in_batch: set[str] = set(
            sync_conn.execute(
                sa.text(f"SELECT name FROM {_MIGRATIONS_TABLE} WHERE batch = :b"),  # noqa: S608 # nosec B608 - trusted constant table name; values bound
                {"b": last_batch},
            ).scalars()
        )
        reverted = 0
        for migration in reversed(migrations):
            if migration.name in in_batch:
                migration.down(schema)
                sync_conn.execute(
                    sa.text(f"DELETE FROM {_MIGRATIONS_TABLE} WHERE name = :n"),  # noqa: S608 # nosec B608 - trusted constant table name; values bound
                    {"n": migration.name},
                )
                reverted += 1
        return reverted


def discover_migrations(paths: Sequence[str], base_path: str = ".") -> list[Migration]:
    """Import every ``*.py`` under each migration directory and instantiate the ``Migration``
    subclasses found, ordered by filename (so timestamp/sequence prefixes apply in order). This is
    how ``load_migrations_from("database/migrations")`` becomes the bound ``migrations`` list that
    ``arvel migrate`` runs. Files are executed as Python (trusted project tree, like config/routes);
    a leading ``_``/``.`` file or a missing directory is skipped.
    """
    import importlib.util
    from pathlib import Path

    instances: list[Migration] = []
    seen_files: set[str] = set()
    for raw in paths:
        directory = Path(raw)
        if not directory.is_absolute():
            directory = Path(base_path) / directory
        directory = directory.resolve()
        if not directory.is_dir():
            continue
        for file in sorted(directory.glob("*.py")):
            if file.name.startswith(("_", ".")) or str(file) in seen_files:
                continue
            seen_files.add(str(file))
            spec = importlib.util.spec_from_file_location(f"_arvel_migration_{file.stem}", file)
            if spec is None or spec.loader is None:  # pragma: no cover - defensive
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for value in vars(module).values():
                if (
                    isinstance(value, type)
                    and issubclass(value, Migration)
                    and value is not Migration
                ):
                    migration = value()
                    # the recorded identifier (one migration per file convention)
                    migration._name = file.stem  # pyright: ignore[reportPrivateUsage]
                    instances.append(migration)
    return instances


__all__ = ["Migration", "Migrator", "Schema", "discover_migrations"]
