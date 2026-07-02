"""Advanced DB (doc 08) — Alembic-driven migrations (upgrade + downgrade). Test-first.

This is doc 08's mandated acceptance check: migrations run through Alembic Operations
(create_table/drop_table), not a raw-SQL migrator.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError

from arvel.database import ConnectionResolver
from arvel.database.migrations import Migration, Migrator


class CreatePosts(Migration):
    def up(self, schema: object) -> None:
        schema.create(  # type: ignore[attr-defined]
            "posts", lambda t: [t.id(), t.string("title"), t.boolean("published"), t.timestamps()]
        )

    def down(self, schema: object) -> None:
        schema.drop("posts")  # type: ignore[attr-defined]


class AddSubtitleToPosts(Migration):
    """Laravel ``Schema::table`` parity — alter an existing table by adding columns."""

    def up(self, schema: object) -> None:
        schema.table(  # type: ignore[attr-defined]
            "posts",
            lambda t: [t.string("subtitle").nullable(), t.integer("views").default(value=0)],
        )

    def down(self, schema: object) -> None:
        schema.drop_column("posts", "subtitle", "views")  # type: ignore[attr-defined]


async def test_schema_table_adds_and_drops_columns() -> None:
    """schema.table() ADDs the blueprint's columns to an existing table (ALTER TABLE), and
    schema.drop_column() removes them — the Schema::table / dropColumn Laravel surface."""
    db = ConnectionResolver()
    migrator = Migrator(db)
    try:
        await migrator.run([CreatePosts(), AddSubtitleToPosts()])
        await db.statement(
            "INSERT INTO posts (title, published, subtitle, views) VALUES ('t', 1, 's', 3)"
        )
        rows = await db.select("SELECT title, subtitle, views FROM posts")
        assert (rows[0]["subtitle"], rows[0]["views"]) == ("s", 3)
        # the default applies when the column isn't named
        await db.statement("INSERT INTO posts (title, published) VALUES ('u', 0)")
        rows = await db.select("SELECT views FROM posts WHERE title = 'u'")
        assert rows[0]["views"] == 0

        await migrator.rollback([AddSubtitleToPosts()])  # last batch only → drops the columns
        rows = await db.select("SELECT * FROM posts")
        assert "subtitle" not in rows[0]
    finally:
        await db.dispose()


async def test_migration_upgrade_then_downgrade() -> None:
    db = ConnectionResolver()
    migrator = Migrator(db)
    try:
        await migrator.run([CreatePosts()])
        # table exists → insert + read work
        await db.statement("INSERT INTO posts (title, published) VALUES ('hello', 1)")
        rows = await db.select("SELECT title FROM posts")
        assert rows[0]["title"] == "hello"

        await migrator.rollback([CreatePosts()])
        # table dropped → querying it now errors
        with pytest.raises(OperationalError):
            await db.select("SELECT * FROM posts")
    finally:
        await db.dispose()
