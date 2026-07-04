"""Alembic-driven migrations (upgrade + downgrade): run through Alembic Operations
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
    """schema.table() ADDs columns to an existing table; schema.drop_column() removes them."""
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


class AddIndexedTagToPosts(Migration):
    """schema.table with an index spec — incl. the GIN→plain-index degrade off Postgres."""

    def up(self, schema: object) -> None:
        def define(t):  # type: ignore[no-untyped-def]
            t.string("tag").nullable()
            t.gin_index("tag")

        schema.table("posts", define)  # type: ignore[attr-defined]

    def down(self, schema: object) -> None:
        schema.drop_column("posts", "tag")  # type: ignore[attr-defined]


async def test_schema_table_creates_indexes_and_degrades_gin_off_postgres() -> None:
    db = ConnectionResolver()
    migrator = Migrator(db)
    try:
        await migrator.run([CreatePosts(), AddIndexedTagToPosts()])  # GIN → plain index on sqlite
        await db.statement("INSERT INTO posts (title, published, tag) VALUES ('t', 1, 'x')")
        rows = await db.select("SELECT tag FROM posts")
        assert rows[0]["tag"] == "x"
    finally:
        await db.dispose()


def test_server_default_clause_covers_the_scalar_literals() -> None:
    """->default() emits DDL defaults for bools/numbers/strings; other values stay client-side."""
    import sqlalchemy as sa

    from arvel.database.schema import ColumnDefinition

    clause = ColumnDefinition._server_default_clause
    assert str(clause(sa, True)) == "TRUE"
    assert str(clause(sa, False)) == "FALSE"
    assert str(clause(sa, 7)) == "7"
    assert str(clause(sa, "it's")) == "'it''s'"
    assert clause(sa, object()) is None
