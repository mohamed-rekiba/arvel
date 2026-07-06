"""arvel.database.migrations — migrations driven by **Alembic**.

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
    server_default_literal,
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
                spec["name"],
                name,
                _index_columns(spec["columns"]),
                unique=spec.get("unique", False),
                postgresql_using=spec["using"],
            )

    def table(self, name: str, define: Callable[[Blueprint], Any]) -> None:
        """ALTER an existing table: every column defined on the
        blueprint is ADDED, and its index specs are created. Column modify/rename aren't covered —
        use ``execute`` for those."""
        blueprint = Blueprint(name)
        define(blueprint)
        for column in blueprint.core_columns():
            self._op.add_column(name, column)
        for spec in blueprint.index_specs():
            if spec["using"] in ("gin", "gist") and self.dialect != "postgresql":
                _warn_pg_only(f"{spec['using'].upper()} index", self.dialect, action="plain index")
            self._op.create_index(
                spec["name"],
                name,
                _index_columns(spec["columns"]),
                unique=spec.get("unique", False),
                postgresql_using=spec["using"],
            )

    def drop_column(self, table: str, *columns: str) -> None:
        """Drop columns from an existing table."""
        for column in columns:
            self._op.drop_column(table, column)

    def drop(self, name: str) -> None:
        self._op.drop_table(name)

    def rename(self, old_table: str, new_table: str) -> None:
        """Rename a table."""
        self._op.rename_table(old_table, new_table)

    def _existing_column(self, table: str, column: str) -> Any:
        """The reflected column dict (SQLAlchemy ``Inspector.get_columns`` shape) for ``column``, or
        ``None`` — MySQL's ``ALTER COLUMN`` needs the *existing* type even for a plain rename/nullable
        change, so ``rename_column``/``change_column`` derive it here rather than asking the caller."""
        import sqlalchemy as sa

        inspector = sa.inspect(self._op.get_bind())
        for col in inspector.get_columns(table):
            if col["name"] == column:
                return col
        return None

    def _alter_column(self, table: str, name: str, **kwargs: Any) -> None:
        existing = self._existing_column(table, name)
        if existing is not None:
            kwargs.setdefault("existing_type", existing["type"])
        # SQLite has no in-place ALTER COLUMN (rename/type/drop-constraint) — batch mode recreates
        # the table under the hood so the same call still works there.
        if self.dialect == "sqlite":
            with self._op.batch_alter_table(table) as batch_op:
                batch_op.alter_column(name, **kwargs)
        else:
            self._op.alter_column(table, name, **kwargs)

    def rename_column(self, table: str, old: str, new: str) -> None:
        """Rename a column, preserving its data."""
        self._alter_column(table, old, new_column_name=new)

    def change_column(
        self,
        table: str,
        name: str,
        *,
        type: Any = None,
        nullable: bool | None = None,
        default: Any = None,
        comment: str | None = None,
    ) -> None:
        """Modify an existing column's type/nullable/default/comment.
        Only the kwargs given are altered; everything else on the column is left as-is."""
        kwargs: dict[str, Any] = {}
        if type is not None:
            kwargs["type_"] = type
        if nullable is not None:
            kwargs["nullable"] = nullable
        if default is not None:
            kwargs["server_default"] = server_default_literal(default)
        if comment is not None:
            kwargs["comment"] = comment
        self._alter_column(table, name, **kwargs)

    def drop_foreign(self, table: str, name: str) -> None:
        """Drop a foreign-key constraint by name."""
        if self.dialect == "sqlite":
            with self._op.batch_alter_table(table) as batch_op:
                batch_op.drop_constraint(name, type_="foreignkey")
        else:
            self._op.drop_constraint(name, table, type_="foreignkey")

    def drop_unique(self, table: str, name: str) -> None:
        """Drop a unique constraint by name."""
        if self.dialect == "sqlite":
            with self._op.batch_alter_table(table) as batch_op:
                batch_op.drop_constraint(name, type_="unique")
        else:
            self._op.drop_constraint(name, table, type_="unique")

    def drop_index(self, table: str, name: str) -> None:
        """Drop an index by name. Native ``DROP INDEX`` on every dialect
        here (including SQLite), so no batch mode is needed."""
        self._op.drop_index(name, table_name=table)

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
    ``migrate:rollback`` reverts the last batch."""

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
        ``db:wipe`` and ``migrate:fresh``. On Postgres, materialized/plain views are dropped first
        (with CASCADE) so a view depending on a table doesn't block the drop. Returns table count."""
        import sqlalchemy as sa
        from sqlalchemy import MetaData

        engine = self._resolver.engine(self._name)
        meta = MetaData()
        async with engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                await conn.execute(
                    sa.text(
                        "DO $$ DECLARE r RECORD; BEGIN "
                        "FOR r IN SELECT matviewname AS n FROM pg_matviews WHERE schemaname='public' LOOP "
                        "EXECUTE 'DROP MATERIALIZED VIEW IF EXISTS \"'||r.n||'\" CASCADE'; END LOOP; "
                        "FOR r IN SELECT viewname AS n FROM pg_views WHERE schemaname='public' LOOP "
                        "EXECUTE 'DROP VIEW IF EXISTS \"'||r.n||'\" CASCADE'; END LOOP; END $$;"
                    )
                )
            await conn.run_sync(meta.reflect)
            await conn.run_sync(meta.drop_all)
        return len(meta.tables)

    @staticmethod
    def _apply(sync_conn: Any, migrations: list[Migration], direction: str) -> int:
        import sqlalchemy as sa
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        # The bookkeeping table as a SQLAlchemy Core Table — every read/write below is a Core
        # construct (no interpolated SQL), so it is dialect-correct and has no injection surface.
        table = sa.Table(
            _MIGRATIONS_TABLE,
            sa.MetaData(),
            sa.Column("name", sa.String(255), primary_key=True),
            sa.Column("batch", sa.Integer, nullable=False),
        )
        table.create(sync_conn, checkfirst=True)
        applied: set[str] = set(sync_conn.execute(sa.select(table.c.name)).scalars())
        context = MigrationContext.configure(sync_conn)
        schema = Schema(Operations(context))

        if direction == "up":
            pending = [m for m in migrations if m.name not in applied]
            if not pending:
                return 0
            next_batch = (
                sync_conn.execute(
                    sa.select(sa.func.coalesce(sa.func.max(table.c.batch), 0))
                ).scalar()
                or 0
            ) + 1
            for migration in pending:
                migration.up(schema)
                sync_conn.execute(sa.insert(table).values(name=migration.name, batch=next_batch))
            return len(pending)

        # down: revert only the most recent batch, in reverse order
        last_batch = sync_conn.execute(sa.select(sa.func.max(table.c.batch))).scalar()
        if last_batch is None:
            return 0
        in_batch: set[str] = set(
            sync_conn.execute(sa.select(table.c.name).where(table.c.batch == last_batch)).scalars()
        )
        reverted = 0
        for migration in reversed(migrations):
            if migration.name in in_batch:
                migration.down(schema)
                sync_conn.execute(sa.delete(table).where(table.c.name == migration.name))
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
