"""Additional Factory coverage — has/for_, count=0 path, _back_ref_of."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Factory, Model, foreign_id, id_, relationship, string
from sqlalchemy.ext.asyncio import AsyncSession


class Author(Model):
    __tablename__ = "authors_m"
    id: int = id_()
    name: str = string(80)
    books: list[Book] = relationship(
        "Book", back_populates="author", lazy="select", init=False, default_factory=list
    )


class Book(Model):
    __tablename__ = "books_m"
    id: int = id_()
    title: str = string(120)
    author_id: int = foreign_id("authors_m.id")
    author: Author | None = relationship(
        "Author", back_populates="books", lazy="select", init=False
    )


class AuthorFactory(Factory[Author]):
    model = Author

    def definition(self) -> dict[str, Any]:
        return {"name": "Ada"}


class BookFactory(Factory[Book]):
    model = Book

    def definition(self) -> dict[str, Any]:
        return {"title": "Untitled"}


async def _setup(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_factory_state_with_callable(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    author = await AuthorFactory().state(lambda: {"name": "Grace"}).create()
    assert isinstance(author, Author)
    assert author.name == "Grace"


async def test_factory_negative_count_rejected() -> None:
    with pytest.raises(ValueError, match="count must be >= 0"):
        AuthorFactory().count(-1)


async def test_factory_for_attaches_parent(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    author = await AuthorFactory().create()
    assert isinstance(author, Author)
    book = await BookFactory().for_("author", author).create()
    assert isinstance(book, Book)
    assert book.author_id == author.id


async def test_factory_has_creates_children(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    created = await AuthorFactory().has("books", BookFactory(), count=2).create()
    author = created if isinstance(created, Author) else created[0]
    # Re-fetch with eager load — `where(id=...).first()` honours `.with_(...)`,
    # whereas `find(pk)` bypasses statement options.
    fresh = await Author.with_("books").where(id=author.id).first()
    assert fresh is not None
    assert len(fresh.books) == 2
