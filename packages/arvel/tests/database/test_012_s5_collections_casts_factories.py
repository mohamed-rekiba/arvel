"""WI-arvel-012 Sprint 5 — Collections, Casts, Factory polish.

Covers FR-012-030 through FR-012-032.

All tests are RED until implementation is complete.
"""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

# ─── Test models ─────────────────────────────────────────────────────────────


class ArticleS5(Model):
    __tablename__ = "articles_s5"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    title: Mapped[str] = mapped_column(String(200))
    score: Mapped[int] = mapped_column(Integer, default=0)
    published: Mapped[int] = mapped_column(Integer, default=0)  # stored as 0/1


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


# ─── FR-012-030: Collection[T] wiring ─────────────────────────────────────────
#
# Behaviour of Collection itself is covered in tests/support/test_collections.py
# (FR-001-007). This single wiring test proves that the QueryBuilder terminal
# methods return the canonical arvel.support.Collection.


async def test_qb_all_returns_canonical_collection(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    from arvel.support import Collection

    await _setup(engine)
    await ArticleS5.create(title="A", score=10)
    await ArticleS5.create(title="B", score=5)
    raw_result = await ArticleS5.all()
    assert isinstance(raw_result, Collection)
    assert isinstance(raw_result, list)
    assert len(raw_result) == 2


# ─── FR-012-031: Standard attribute casts ─────────────────────────────────────


async def test_boolean_cast_from_int(engine: AsyncEngine, session: AsyncSession) -> None:
    class CastBool(Model):
        __tablename__ = "cast_bool"
        __casts__ = {"published": "boolean"}
        id: Mapped[int] = mapped_column(
            Integer, primary_key=True, autoincrement=True, init=False, default=None
        )
        published: Mapped[int] = mapped_column(Integer, default=0)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    item = await CastBool.create(published=1)
    fetched = await CastBool.find(item.id)
    assert fetched.published is True


async def test_integer_cast(engine: AsyncEngine, session: AsyncSession) -> None:
    class CastInt(Model):
        __tablename__ = "cast_int"
        __casts__ = {"score": "integer"}
        id: Mapped[int] = mapped_column(
            Integer, primary_key=True, autoincrement=True, init=False, default=None
        )
        score: Mapped[str] = mapped_column(String(20), default="0")

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    item = await CastInt.create(score="42")
    fetched = await CastInt.find(item.id)
    assert isinstance(fetched.score, int)
    assert fetched.score == 42


async def test_dict_cast_from_json(engine: AsyncEngine, session: AsyncSession) -> None:
    class CastDict(Model):
        __tablename__ = "cast_dict"
        __casts__ = {"meta": "dict"}
        id: Mapped[int] = mapped_column(
            Integer, primary_key=True, autoincrement=True, init=False, default=None
        )
        meta: Mapped[str] = mapped_column(String(500), default="{}")

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    item = await CastDict.create(meta='{"key": "value"}')
    fetched = await CastDict.find(item.id)
    meta: dict[str, Any] = fetched.meta
    assert isinstance(meta, dict)
    assert meta["key"] == "value"


def test_invalid_cast_literal_raises_at_definition() -> None:
    # Defining the class is the side effect under test: ``Model``'s metaclass
    # validates ``__casts__`` during class creation and raises. ``type(...)``
    # creates the class without binding a Python-level name, which keeps
    # pyright from reporting an "unused" class.
    with pytest.raises(ValueError):
        type(
            "BadCast",
            (Model,),
            {
                "__tablename__": "bad_cast",
                "__casts__": {"field": "not_a_valid_cast"},
                "__annotations__": {"id": "Mapped[int]", "field": "Mapped[str]"},
                "id": mapped_column(
                    Integer, primary_key=True, autoincrement=True, init=False, default=None
                ),
                "field": mapped_column(String(80), default="x"),
            },
        )


# ─── FR-012-032: Factory polish ───────────────────────────────────────────────


async def test_factory_sequence_produces_distinct_values(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    from arvel.database.factories import Factory

    class ArticleFactory(Factory[ArticleS5]):
        model = ArticleS5

        def definition(self) -> dict[str, Any]:
            return {"title": "default", "score": 0}

    await _setup(engine)

    factory = ArticleFactory().sequence("title", lambda n: f"article_{n}")
    articles = await factory.count(3).create()
    assert isinstance(articles, list)
    titles = {a.title for a in articles}
    assert len(titles) == 3  # all distinct


async def test_factory_after_creating_callback(engine: AsyncEngine, session: AsyncSession) -> None:
    from arvel.database.factories import Factory

    class CallbackFactory(Factory[ArticleS5]):
        model = ArticleS5

        def definition(self) -> dict[str, Any]:
            return {"title": "cb_article", "score": 0}

    await _setup(engine)
    created_ids: list[int] = []

    factory = CallbackFactory().after_creating(lambda a, _faker: created_ids.append(a.id))
    _ = await factory.count(2).create()
    assert len(created_ids) == 2
    assert all(aid is not None for aid in created_ids)


async def test_factory_after_making_callback(engine: AsyncEngine, session: AsyncSession) -> None:
    from arvel.database.factories import Factory

    class MakeFactory(Factory[ArticleS5]):
        model = ArticleS5

        def definition(self) -> dict[str, Any]:
            return {"title": "made", "score": 0}

    await _setup(engine)
    made_titles: list[str] = []

    factory = MakeFactory().after_making(lambda a, _faker: made_titles.append(a.title))
    instances = factory.count(2).make()
    assert isinstance(instances, list)
    assert len(made_titles) == 2
    for inst in instances:
        assert inst.id is None  # not persisted


async def test_factory_recycle_reuses_instances(engine: AsyncEngine, session: AsyncSession) -> None:
    from arvel.database.factories import Factory

    class RecycleFactory(Factory[ArticleS5]):
        model = ArticleS5

        def definition(self) -> dict[str, Any]:
            return {"title": "recycled", "score": 0}

    await _setup(engine)

    existing = await ArticleS5.create(title="existing_recycle", score=5)
    factory = RecycleFactory().recycle([existing])
    result = factory.make()
    # recycle means: when a FK column would normally create a new model,
    # pick from existing instead. Smoke test: no exception.
    assert result is not None
