"""Relations and chunking work with non-integer (string/uuid) primary keys (round H5)."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Author(Model):
    __primary_key__ = "id"
    __fields__ = {"id": str, "name": str}  # explicit string PK
    __fillable__ = ["id", "name"]

    def books(self) -> object:
        return self.belongs_to_many(Book)


class Book(Model):
    __primary_key__ = "id"
    __fields__ = {"id": str, "title": str}
    __fillable__ = ["id", "title"]


_md = sa.MetaData()
author_book = sa.Table(
    "author_book", _md, sa.Column("author_id", sa.String), sa.Column("book_id", sa.String)
)


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Author, Book):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(author_book))
    return db


async def test_belongs_to_many_with_string_pk() -> None:
    db = await _setup()
    try:
        a = await Author.create(id="a-1", name="Ada")
        b1 = await Book.create(id="b-1", title="One")
        b2 = await Book.create(id="b-2", title="Two")
        await a.books().attach(b1.id)
        await a.books().attach(b2.id)

        books = await a.books().get()
        assert {b.title for b in books} == {"One", "Two"}
        assert await a.books().count() == 2
    finally:
        await db.dispose()


async def test_chunk_by_id_with_string_pk() -> None:
    db = await _setup()
    try:
        for i in range(5):
            await Book.create(id=f"b-{i}", title=f"t{i}")
        seen: list[str] = []

        async def collect(rows: Any) -> None:
            for r in rows:
                seen.append(r.id)

        await Book.query().chunk_by_id(2, collect)
        assert sorted(seen) == ["b-0", "b-1", "b-2", "b-3", "b-4"]
    finally:
        await db.dispose()
