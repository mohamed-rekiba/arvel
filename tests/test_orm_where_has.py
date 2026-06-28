"""ORM (doc 07) — relationship existence queries: has / where_has / doesnt_have. Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Author(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def books(self) -> object:
        return self.has_many(Book)


class Book(Model):
    __fields__ = {"title": str, "author_id": int, "published": bool}
    __fillable__ = ["title", "author_id", "published"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Author, Book):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_has_returns_only_parents_with_children() -> None:
    db = await _setup()
    try:
        prolific = await Author.create(name="Prolific")
        await Author.create(name="Silent")  # no books
        await Book.create(title="A", author_id=prolific.id, published=True)

        names = {a.name for a in await Author.has("books").get()}
        assert names == {"Prolific"}
    finally:
        await db.dispose()


async def test_doesnt_have_returns_childless_parents() -> None:
    db = await _setup()
    try:
        prolific = await Author.create(name="Prolific")
        await Author.create(name="Silent")
        await Book.create(title="A", author_id=prolific.id, published=True)

        names = {a.name for a in await Author.doesnt_have("books").get()}
        assert names == {"Silent"}
    finally:
        await db.dispose()


async def test_where_has_applies_callback_constraint() -> None:
    db = await _setup()
    try:
        published_author = await Author.create(name="Published")
        draft_author = await Author.create(name="Draft")
        await Book.create(title="Live", author_id=published_author.id, published=True)
        await Book.create(title="WIP", author_id=draft_author.id, published=False)

        names = {
            a.name for a in await Author.where_has("books", lambda q: q.where(published=True)).get()
        }
        assert names == {"Published"}  # Draft has only an unpublished book
    finally:
        await db.dispose()
