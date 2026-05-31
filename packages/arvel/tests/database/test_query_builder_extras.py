"""first_where, where_relation, and Eloquent-faithful bulk update/increment.

Bulk update/increment/decrement/soft-delete touch updated_at when the model is
timestamped; increment/decrement accept extra columns and return rows affected.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from arvel.database import Model, Timestamps, foreign_id, id_, integer, relationship, string
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class QbeAuthor(Model, Timestamps):
    __tablename__ = "qbe_authors"
    id: int = id_()
    name: str = string(80)
    hits: int = integer(default=0)
    books: list[QbeBook] = relationship(
        "QbeBook", back_populates="author", init=False, default_factory=list
    )


class QbeBook(Model, Timestamps):
    __tablename__ = "qbe_books"
    id: int = id_()
    title: str = string(120)
    genre: str = string(40, default="fiction")
    author_id: int | None = foreign_id("qbe_authors.id", nullable=True)
    author: QbeAuthor | None = relationship("QbeAuthor", back_populates="books", init=False)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_first_where_returns_match(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await QbeAuthor.create(name="Ada")
    await QbeAuthor.create(name="Grace")

    found = await QbeAuthor.first_where(QbeAuthor.name == "Grace")
    assert found is not None
    assert found.name == "Grace"


async def test_first_where_returns_none_when_no_match(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    await QbeAuthor.create(name="Ada")
    assert await QbeAuthor.first_where(QbeAuthor.name == "nobody") is None


async def test_where_relation_filters_by_related_column(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    a1 = await QbeAuthor.create(name="A1")
    a2 = await QbeAuthor.create(name="A2")
    await QbeBook.create(title="Sci", genre="scifi", author_id=a1.id)
    await QbeBook.create(title="Fic", genre="fiction", author_id=a2.id)

    rows = await QbeAuthor.where_relation("books", "genre", "scifi").all()
    assert [a.name for a in rows] == ["A1"]


async def test_increment_returns_rowcount_and_touches_updated_at(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    author = await QbeAuthor.create(name="Ada", hits=0)
    # Push updated_at into the past, then read it back so both sides are naive (SQLite).
    await QbeAuthor.where(QbeAuthor.id == author.id).update(
        {"updated_at": datetime.now(UTC) - timedelta(days=1)}
    )
    await session.refresh(author)
    before = author.updated_at

    n = await QbeAuthor.where(QbeAuthor.id == author.id).increment("hits", 5)
    assert n == 1
    await session.refresh(author)
    assert author.hits == 5
    assert author.updated_at > before


async def test_increment_with_extra_columns(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    author = await QbeAuthor.create(name="Ada", hits=0)

    await QbeAuthor.where(QbeAuthor.id == author.id).increment("hits", 1, extra={"name": "Renamed"})
    await session.refresh(author)
    assert author.hits == 1
    assert author.name == "Renamed"


async def test_bulk_update_touches_updated_at(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    author = await QbeAuthor.create(name="Ada")
    await QbeAuthor.where(QbeAuthor.id == author.id).update(
        {"updated_at": datetime.now(UTC) - timedelta(days=1)}
    )
    await session.refresh(author)
    before = author.updated_at

    await QbeAuthor.where(QbeAuthor.id == author.id).update({"name": "Ada Lovelace"})
    await session.refresh(author)
    assert author.updated_at > before
