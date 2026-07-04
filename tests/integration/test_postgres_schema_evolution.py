"""Schema evolution (doc 10) against real PostgreSQL: rename_column/change_column round-trip through
migrate -> inspect -> rollback, and migrate:refresh replays the full migration set cleanly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver
from arvel.database.migrations import Migration, Migrator

pytestmark = pytest.mark.integration


async def _inspect(db: ConnectionResolver, fn: Callable[[Any], Any]) -> Any:
    async with db.engine().connect() as conn:
        return await conn.run_sync(fn)


class CreateWidgets(Migration):
    def up(self, schema: object) -> None:
        schema.create(  # type: ignore[attr-defined]
            "pg_widgets", lambda t: [t.id(), t.string("name"), t.integer("count").default(value=0)]
        )

    def down(self, schema: object) -> None:
        schema.drop("pg_widgets")  # type: ignore[attr-defined]


class RenameNameToTitle(Migration):
    def up(self, schema: object) -> None:
        schema.rename_column("pg_widgets", "name", "title")  # type: ignore[attr-defined]

    def down(self, schema: object) -> None:
        schema.rename_column("pg_widgets", "title", "name")  # type: ignore[attr-defined]


class ChangeCountNullable(Migration):
    def up(self, schema: object) -> None:
        schema.change_column("pg_widgets", "count", nullable=True, default=9)  # type: ignore[attr-defined]

    def down(self, schema: object) -> None:
        schema.change_column("pg_widgets", "count", nullable=False, default=0)  # type: ignore[attr-defined]


async def test_rename_and_change_column_round_trip_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    migrator = Migrator(db)
    try:
        await migrator.run([CreateWidgets()])
        await db.statement("INSERT INTO pg_widgets (name, count) VALUES ('gizmo', 3)")

        await migrator.run([CreateWidgets(), RenameNameToTitle(), ChangeCountNullable()])
        columns = await _inspect(db, lambda conn: sa.inspect(conn).get_columns("pg_widgets"))
        by_name = {c["name"]: c for c in columns}
        assert "title" in by_name and "name" not in by_name
        assert by_name["count"]["nullable"] is True

        rows = await db.select("SELECT title, count FROM pg_widgets")
        assert (rows[0]["title"], rows[0]["count"]) == ("gizmo", 3)

        await db.statement("INSERT INTO pg_widgets (title) VALUES ('widget2')")
        rows = await db.select("SELECT count FROM pg_widgets WHERE title = 'widget2'")
        assert rows[0]["count"] == 9

        await migrator.rollback([ChangeCountNullable()])
        columns = await _inspect(db, lambda conn: sa.inspect(conn).get_columns("pg_widgets"))
        by_name = {c["name"]: c for c in columns}
        assert by_name["count"]["nullable"] is False

        await migrator.rollback([RenameNameToTitle()])
        columns = await _inspect(db, lambda conn: sa.inspect(conn).get_columns("pg_widgets"))
        by_name = {c["name"]: c for c in columns}
        assert "name" in by_name and "title" not in by_name
    finally:
        await migrator.drop_all()
        await db.dispose()


async def test_migrate_refresh_replays_cleanly_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    migrator = Migrator(db)
    migrations = [CreateWidgets(), RenameNameToTitle()]
    try:
        await migrator.run(migrations)
        await db.statement("INSERT INTO pg_widgets (title, count) VALUES ('stale', 1)")

        await migrator.rollback(migrations)
        applied = await migrator.run(migrations)
        assert applied == len(migrations)

        rows = await db.select("SELECT * FROM pg_widgets")
        assert rows == []  # the stale row is gone — a clean re-migrated state

        columns = await _inspect(db, lambda conn: sa.inspect(conn).get_columns("pg_widgets"))
        assert {c["name"] for c in columns} >= {"id", "title", "count"}
    finally:
        await migrator.drop_all()
        await db.dispose()
