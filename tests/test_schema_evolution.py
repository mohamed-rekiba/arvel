"""Schema evolution (doc 10): rename_column/change_column/rename/drop_foreign/drop_index/drop_unique
— against in-memory SQLite (which routes column-level changes through Alembic batch mode; table
rename and drop_index are native everywhere)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import sqlalchemy as sa

from arvel.database import ConnectionResolver
from arvel.database.migrations import Migration, Migrator


async def _inspect(db: ConnectionResolver, fn: Callable[[Any], Any]) -> Any:
    async with db.engine().connect() as conn:
        return await conn.run_sync(fn)


class CreateWidgets(Migration):
    def up(self, schema: object) -> None:
        schema.create(  # type: ignore[attr-defined]
            "widgets", lambda t: [t.id(), t.string("name"), t.integer("count").default(value=0)]
        )

    def down(self, schema: object) -> None:
        schema.drop("widgets")  # type: ignore[attr-defined]


class RenameNameToTitle(Migration):
    def up(self, schema: object) -> None:
        schema.rename_column("widgets", "name", "title")  # type: ignore[attr-defined]

    def down(self, schema: object) -> None:
        schema.rename_column("widgets", "title", "name")  # type: ignore[attr-defined]


async def test_rename_column_preserves_data_and_rolls_back() -> None:
    db = ConnectionResolver()
    migrator = Migrator(db)
    try:
        await migrator.run([CreateWidgets()])
        await db.statement("INSERT INTO widgets (name, count) VALUES ('gizmo', 3)")

        await migrator.run([CreateWidgets(), RenameNameToTitle()])
        rows = await db.select("SELECT title, count FROM widgets")
        assert (rows[0]["title"], rows[0]["count"]) == ("gizmo", 3)

        await migrator.rollback([RenameNameToTitle()])
        rows = await db.select("SELECT name FROM widgets")
        assert rows[0]["name"] == "gizmo"
    finally:
        await db.dispose()


class ChangeCountNullableAndDefault(Migration):
    def up(self, schema: object) -> None:
        schema.change_column("widgets", "count", nullable=True, default=7)  # type: ignore[attr-defined]

    def down(self, schema: object) -> None:
        schema.change_column("widgets", "count", nullable=False, default=0)  # type: ignore[attr-defined]


async def test_change_column_alters_nullable_and_default_existing_rows_survive() -> None:
    db = ConnectionResolver()
    migrator = Migrator(db)
    try:
        await migrator.run([CreateWidgets()])
        await db.statement("INSERT INTO widgets (name, count) VALUES ('a', 1)")

        await migrator.run([CreateWidgets(), ChangeCountNullableAndDefault()])
        await db.statement("INSERT INTO widgets (name) VALUES ('b')")  # count now defaults to 7
        rows = await db.select("SELECT name, count FROM widgets ORDER BY name")
        assert [(r["name"], r["count"]) for r in rows] == [("a", 1), ("b", 7)]
    finally:
        await db.dispose()


class RenameWidgetsTable(Migration):
    def up(self, schema: object) -> None:
        schema.rename("widgets", "gadgets")  # type: ignore[attr-defined]

    def down(self, schema: object) -> None:
        schema.rename("gadgets", "widgets")  # type: ignore[attr-defined]


async def test_rename_table() -> None:
    db = ConnectionResolver()
    migrator = Migrator(db)
    try:
        await migrator.run([CreateWidgets()])
        await db.statement("INSERT INTO widgets (name, count) VALUES ('x', 1)")

        await migrator.run([CreateWidgets(), RenameWidgetsTable()])
        rows = await db.select("SELECT name FROM gadgets")
        assert rows[0]["name"] == "x"

        await migrator.rollback([RenameWidgetsTable()])
        rows = await db.select("SELECT name FROM widgets")
        assert rows[0]["name"] == "x"
    finally:
        await db.dispose()


class CreateTaggedWidgets(Migration):
    """A table with an .index() column — its default SQLAlchemy-assigned index name is
    ``ix_<table>_<column>``, so drop_index has a stable name to target."""

    def up(self, schema: object) -> None:
        schema.create(  # type: ignore[attr-defined]
            "tagged_widgets", lambda t: [t.id(), t.string("tag").index()]
        )

    def down(self, schema: object) -> None:
        schema.drop("tagged_widgets")  # type: ignore[attr-defined]


class DropTagIndex(Migration):
    def up(self, schema: object) -> None:
        schema.drop_index("tagged_widgets", "ix_tagged_widgets_tag")  # type: ignore[attr-defined]

    def down(self, schema: object) -> None:
        pass  # not needed for this test


async def test_drop_index() -> None:
    db = ConnectionResolver()
    migrator = Migrator(db)
    try:
        await migrator.run([CreateTaggedWidgets()])
        indexes = await _inspect(db, lambda conn: sa.inspect(conn).get_indexes("tagged_widgets"))
        assert any(ix["name"] == "ix_tagged_widgets_tag" for ix in indexes)

        await migrator.run([CreateTaggedWidgets(), DropTagIndex()])
        indexes = await _inspect(db, lambda conn: sa.inspect(conn).get_indexes("tagged_widgets"))
        assert not any(ix["name"] == "ix_tagged_widgets_tag" for ix in indexes)
    finally:
        await db.dispose()


class CreateNamedConstraints(Migration):
    """Blueprint has no named-constraint builder yet, so this uses raw DDL to set up fixtures with
    stable constraint names for drop_foreign/drop_unique to target."""

    def up(self, schema: object) -> None:
        schema.execute(  # type: ignore[attr-defined]
            sa.text("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT UNIQUE)")
        )
        schema.execute(  # type: ignore[attr-defined]
            sa.text(
                "CREATE TABLE named_books (id INTEGER PRIMARY KEY, author_id INTEGER, "
                "CONSTRAINT fk_named_books_author FOREIGN KEY(author_id) REFERENCES authors(id))"
            )
        )
        schema.execute(  # type: ignore[attr-defined]
            sa.text(
                "CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT, "
                "CONSTRAINT uq_tags_name UNIQUE(name))"
            )
        )

    def down(self, schema: object) -> None:
        schema.drop("named_books")  # type: ignore[attr-defined]
        schema.drop("authors")  # type: ignore[attr-defined]
        schema.drop("tags")  # type: ignore[attr-defined]


class DropNamedConstraints(Migration):
    def up(self, schema: object) -> None:
        schema.drop_foreign("named_books", "fk_named_books_author")  # type: ignore[attr-defined]
        schema.drop_unique("tags", "uq_tags_name")  # type: ignore[attr-defined]

    def down(self, schema: object) -> None:
        pass  # not needed for this test


async def test_drop_foreign_and_drop_unique() -> None:
    db = ConnectionResolver()
    migrator = Migrator(db)
    try:
        await migrator.run([CreateNamedConstraints()])
        fks = await _inspect(db, lambda conn: sa.inspect(conn).get_foreign_keys("named_books"))
        assert any(fk["name"] == "fk_named_books_author" for fk in fks)
        uqs = await _inspect(db, lambda conn: sa.inspect(conn).get_unique_constraints("tags"))
        assert any(uq["name"] == "uq_tags_name" for uq in uqs)

        await migrator.run([CreateNamedConstraints(), DropNamedConstraints()])
        fks = await _inspect(db, lambda conn: sa.inspect(conn).get_foreign_keys("named_books"))
        assert not any(fk["name"] == "fk_named_books_author" for fk in fks)
        uqs = await _inspect(db, lambda conn: sa.inspect(conn).get_unique_constraints("tags"))
        assert not any(uq["name"] == "uq_tags_name" for uq in uqs)
    finally:
        await db.dispose()
