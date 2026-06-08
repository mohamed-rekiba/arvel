"""Eloquent-parity: or_* OR-onto-chain + clause polish bundle."""

from __future__ import annotations

from typing import cast

from arvel.database import Model, id_, integer, string
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class Widget(Model):
    __tablename__ = "polish_widgets"
    id: int = id_()
    name: str = string(40, default="")
    tag: str = string(20, default="")
    qty: int = integer(default=0)


async def _seed(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    await Widget.create(name="a", tag="x", qty=1)
    await Widget.create(name="b", tag="y", qty=5)
    await Widget.create(name="c", tag="x", qty=9)
    await Widget.create(name="d", tag="z", qty=0)


async def test_or_where_in_ors_onto_chain(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    # qty == 1 OR tag IN (y) -> a (qty 1), b (tag y)
    rows = await Widget.where(qty=1).or_where_in("tag", ["y"]).order_by("name").all()
    assert [r.name for r in rows] == ["a", "b"]


async def test_or_where_ors_onto_chain(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    # name == 'a' OR tag == 'z' -> a, d (proves OR onto the chain, not AND)
    rows = (
        await Widget.where(name="a").or_where(Widget.__table__.c.tag == "z").order_by("name").all()
    )
    assert [r.name for r in rows] == ["a", "d"]


async def test_or_where_between(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    # name == 'a' OR qty BETWEEN 8 AND 10 -> a, c
    rows = await Widget.where(name="a").or_where_between("qty", 8, 10).order_by("name").all()
    assert [r.name for r in rows] == ["a", "c"]


async def test_explicit_grouping_precedence(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    # (qty == 1 OR qty == 9) AND tag == 'x' -> a, c   (explicit grouping)
    rows = (
        await Widget.where(qty=1)
        .or_where(Widget.__table__.c.qty == 9)
        .where(tag="x")
        .order_by("name")
        .all()
    )
    assert [r.name for r in rows] == ["a", "c"]


async def test_order_by_desc_and_reorder(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    desc_names = [r.name for r in await Widget.order_by_desc("qty").all()]
    assert desc_names == ["c", "b", "a", "d"]
    # reorder drops the desc and applies ascending qty
    re_names = [r.name for r in await Widget.order_by_desc("qty").reorder("qty").all()]
    assert re_names == ["d", "a", "b", "c"]


async def test_in_random_order_returns_all(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await Widget.in_random_order().all()
    assert sorted(r.name for r in rows) == ["a", "b", "c", "d"]


async def test_having_operator_form(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    from sqlalchemy import func

    rows = await Widget.group_by("tag").having(func.count(), ">", 1).select("tag").all()

    def _tag(row: object) -> object:
        if isinstance(row, dict):
            return cast("dict[str, object]", row)["tag"]
        if isinstance(row, tuple):
            return cast("tuple[object, ...]", row)[0]
        return row

    # only tag 'x' has more than one row
    assert [_tag(r) for r in rows] == ["x"]


async def test_pluck_with_key_returns_dict(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    mapping = await Widget.pluck("name", "qty")
    assert isinstance(mapping, dict)
    assert mapping[1] == "a"
    assert mapping[9] == "c"


async def test_pluck_without_key_returns_list(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    names = await Widget.pluck("name")
    assert isinstance(names, list)
    assert sorted(names) == ["a", "b", "c", "d"]


async def test_count_column_skips_nulls(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    assert await Widget.count() == 4
    assert await Widget.count("name") == 4


async def test_sum_empty_returns_zero(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    assert await Widget.where(name="nope").sum("qty") == 0
    assert await Widget.sum("qty") == 15
