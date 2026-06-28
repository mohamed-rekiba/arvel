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
    Blueprint,
    create_extension,
    create_materialized_view,
    create_view,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from arvel.database.connections import ConnectionResolver


class Schema:
    """Operations facade bound to an Alembic ``Operations`` instance."""

    def __init__(self, op: Any) -> None:
        self._op = op

    def create(self, name: str, define: Callable[[Blueprint], Any]) -> None:
        blueprint = Blueprint(name)
        define(blueprint)
        self._op.create_table(name, *blueprint.core_columns())
        for spec in blueprint.index_specs():  # GIN/GiST → a separate create_index op
            self._op.create_index(
                spec["name"], name, list(spec["columns"]), postgresql_using=spec["using"]
            )

    def drop(self, name: str) -> None:
        self._op.drop_table(name)

    def execute(self, statement: Any) -> None:
        self._op.execute(statement)

    def create_view(self, name: str, selectable: Any) -> None:
        self._op.execute(create_view(name, selectable))

    def create_materialized_view(self, name: str, selectable: Any) -> None:
        self._op.execute(create_materialized_view(name, selectable))

    def create_extension(self, name: str) -> None:
        self._op.execute(create_extension(name))


class Migration:
    """Base migration: subclass and implement ``up`` and ``down``."""

    def up(self, schema: Schema) -> None:
        raise NotImplementedError

    def down(self, schema: Schema) -> None:
        raise NotImplementedError


class Migrator:
    """Runs migrations through Alembic on the write connection."""

    def __init__(self, resolver: ConnectionResolver, name: str | None = None) -> None:
        self._resolver = resolver
        self._name = name

    async def run(self, migrations: Sequence[Migration]) -> None:
        async with self._resolver.engine(self._name).begin() as conn:
            await conn.run_sync(self._apply, list(migrations), "up")

    async def rollback(self, migrations: Sequence[Migration]) -> None:
        async with self._resolver.engine(self._name).begin() as conn:
            await conn.run_sync(self._apply, list(reversed(list(migrations))), "down")

    @staticmethod
    def _apply(sync_conn: Any, migrations: list[Migration], direction: str) -> None:
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        context = MigrationContext.configure(sync_conn)
        schema = Schema(Operations(context))
        for migration in migrations:
            if direction == "up":
                migration.up(schema)
            else:
                migration.down(schema)


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
                    instances.append(value())
    return instances


__all__ = ["Migration", "Migrator", "Schema", "discover_migrations"]
