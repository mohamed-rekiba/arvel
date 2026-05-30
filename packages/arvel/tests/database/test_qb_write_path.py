"""Eloquent-parity (backlog 005, S8): write-path completeness.

insert_or_ignore, single-statement upsert (returns count), truncate, insert_using,
increment_each / decrement_each.
"""

from __future__ import annotations

from arvel.database import Model
from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class WTag(Model):
    __tablename__ = "w_tags"
    __table_args__ = (UniqueConstraint("slug", name="uq_w_tags_slug"),)
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)


class WCounter(Model):
    __tablename__ = "w_counters"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    misses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class WSource(Model):
    __tablename__ = "w_sources"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    label: Mapped[str] = mapped_column(String(80), nullable=False)


class WDest(Model):
    __tablename__ = "w_dests"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_insert_or_ignore_skips_conflicts(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    await WTag.create(slug="a", label="original")

    await WTag.insert_or_ignore(
        [{"slug": "a", "label": "dupe"}, {"slug": "b", "label": "fresh"}]
    )

    rows = {t.slug: t.label for t in await WTag.order_by("slug").all()}
    assert rows == {"a": "original", "b": "fresh"}


async def test_upsert_single_statement_returns_count(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)

    inserted = await WTag.upsert(
        [{"slug": "x", "label": "one"}, {"slug": "y", "label": "two"}],
        unique_by=["slug"],
        update=["label"],
    )
    assert inserted >= 1
    assert await WTag.count() == 2

    await WTag.upsert(
        [{"slug": "x", "label": "updated"}],
        unique_by=["slug"],
        update=["label"],
    )
    x = await WTag.where(WTag.slug == "x").first()
    assert x is not None
    assert x.label == "updated"
    assert await WTag.count() == 2


async def test_truncate_empties_table(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    await WTag.create(slug="t1", label="a")
    await WTag.create(slug="t2", label="b")
    assert await WTag.count() == 2

    await WTag.truncate()

    assert await WTag.count() == 0


async def test_insert_using_from_select(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    await WSource.create(label="from-source-1")
    await WSource.create(label="from-source-2")

    affected = await WDest.insert_using(["name"], WSource.query().select("label"))
    assert affected == 2

    names = sorted(d.name for d in await WDest.all())
    assert names == ["from-source-1", "from-source-2"]


async def test_increment_each_bumps_multiple(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    await WCounter.create(name="c", hits=1, misses=1)

    affected = await WCounter.where(WCounter.name == "c").increment_each(
        {"hits": 5, "misses": 2}
    )
    assert affected == 1

    c = await WCounter.where(WCounter.name == "c").first()
    assert c is not None
    assert (c.hits, c.misses) == (6, 3)


async def test_decrement_each_bumps_multiple(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    await WCounter.create(name="d", hits=10, misses=10)

    await WCounter.where(WCounter.name == "d").decrement_each({"hits": 3, "misses": 1})

    d = await WCounter.where(WCounter.name == "d").first()
    assert d is not None
    assert (d.hits, d.misses) == (7, 9)


