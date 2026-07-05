"""Relationship factories, doc 10.

`has`/`for_`/`recycle` are wired through `create`/`create_many` only (they need a persisted parent
row) — against in-memory SQLite.
"""

from __future__ import annotations

from typing import Any, ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Factory, Model


class Author(Model):
    __fields__: ClassVar[dict[str, Any]] = {"name": str}
    __fillable__: ClassVar[list[str]] = ["name"]

    def books(self) -> Any:
        return self.has_many(Book)


class Book(Model):
    __fields__: ClassVar[dict[str, Any]] = {"author_id": int, "title": str}
    __fillable__: ClassVar[list[str]] = ["author_id", "title"]

    def author(self) -> Any:
        return self.belongs_to(Author)


class AuthorFactory(Factory[Author]):
    model = Author

    def definition(self) -> dict[str, Any]:
        return {"name": "Ada"}


class BookFactory(Factory[Book]):
    model = Book

    def definition(self) -> dict[str, Any]:
        return {"title": "Untitled"}


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Author, Book):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_has_creates_related_rows_with_fk_set() -> None:
    db = await _db()
    try:
        author = await AuthorFactory().has(BookFactory(), "books", 2).create()
        books = await Book.where("author_id", "=", author.id).get()
        assert len(books) == 2
        assert all(b.author_id == author.id for b in books)
    finally:
        await db.dispose()


async def test_has_with_a_count_batch_uses_its_count() -> None:
    db = await _db()
    try:
        author = await AuthorFactory().has(BookFactory().count(3), "books").create()
        books = await Book.where("author_id", "=", author.id).get()
        assert len(books) == 3
    finally:
        await db.dispose()


async def test_for_sets_belongs_to_fk() -> None:
    db = await _db()
    try:
        book = await BookFactory().for_(AuthorFactory(), "author").create()
        assert book.author_id is not None
        author = await Author.find(book.author_id)
        assert author is not None and author.name == "Ada"
    finally:
        await db.dispose()


async def test_for_explicit_override_wins_over_derived_fk() -> None:
    db = await _db()
    try:
        existing = await AuthorFactory().create(name="Explicit")
        book = await BookFactory().for_(AuthorFactory(), "author").create(author_id=existing.id)
        assert book.author_id == existing.id
    finally:
        await db.dispose()


async def test_recycle_reuses_a_single_instance_across_creates() -> None:
    db = await _db()
    try:
        shared = await AuthorFactory().create(name="Shared")
        factory = BookFactory().recycle(shared).for_(AuthorFactory(), "author")
        book1 = await factory.create()
        book2 = await factory.create()
        assert book1.author_id == shared.id
        assert book2.author_id == shared.id
        assert len(await Author.all()) == 1  # no extra parent rows created
    finally:
        await db.dispose()


async def test_recycle_then_for_then_count_batch() -> None:
    """The `.recycle().for_().count().create()` chain (count() wraps last, in a FactoryBatch)."""
    db = await _db()
    try:
        shared = await AuthorFactory().create(name="Shared")
        books = (
            await BookFactory().recycle(shared).for_(AuthorFactory(), "author").count(3).create()
        )
        assert len(books) == 3
        assert all(b.author_id == shared.id for b in books)
        assert len(await Author.all()) == 1
    finally:
        await db.dispose()


async def test_after_creating_runs_once_per_created_model_in_order() -> None:
    db = await _db()
    try:
        calls: list[str] = []
        factory = (
            AuthorFactory()
            .after_creating(lambda a: calls.append(f"first:{a.name}"))
            .after_creating(lambda a: calls.append(f"second:{a.name}"))
        )
        await factory.create(name="Grace")
        assert calls == ["first:Grace", "second:Grace"]

        calls.clear()
        await factory.count(2).create(name="Grace")
        assert calls == ["first:Grace", "second:Grace", "first:Grace", "second:Grace"]
    finally:
        await db.dispose()


async def test_after_making_runs_before_persistence() -> None:
    db = await _db()
    try:
        seen_exists: list[bool] = []
        author = (
            await AuthorFactory()
            .after_making(lambda a: seen_exists.append(a._exists))
            .create(name="Marie")
        )
        assert seen_exists == [False]  # not yet persisted when after_making ran
        assert author._exists is True
    finally:
        await db.dispose()


async def test_after_creating_supports_async_callbacks() -> None:
    db = await _db()
    try:
        touched: list[int] = []

        async def bump(author: Author) -> None:
            touched.append(author.id)

        await AuthorFactory().after_creating(bump).create()
        assert len(touched) == 1
    finally:
        await db.dispose()


def test_model_factory_resolves_by_convention() -> None:
    factory = Author.factory()
    assert isinstance(factory, AuthorFactory)


async def test_model_factory_count_create_chain() -> None:
    db = await _db()
    try:
        authors = await Author.factory().count(3).create()
        assert len(authors) == 3
    finally:
        await db.dispose()


class Pseudonym(Model):
    __fields__: ClassVar[dict[str, Any]] = {"name": str}
    __fillable__: ClassVar[list[str]] = ["name"]


class ExplicitPseudonymFactory(Factory[Pseudonym]):
    model = Pseudonym

    def definition(self) -> dict[str, Any]:
        return {"name": "Anon"}


def test_model_factory_honors_explicit_override() -> None:
    """`__factory__` wins over the convention-registered factory (there isn't one here anyway)."""
    Pseudonym.__factory__ = ExplicitPseudonymFactory
    try:
        assert isinstance(Pseudonym.factory(), ExplicitPseudonymFactory)
    finally:
        Pseudonym.__factory__ = None


def test_model_factory_raises_when_unregistered() -> None:
    class Orphan(Model):
        __fields__: ClassVar[dict[str, Any]] = {"name": str}

    try:
        Orphan.factory()
    except LookupError as exc:
        assert "Orphan" in str(exc)
    else:
        raise AssertionError("expected LookupError")
