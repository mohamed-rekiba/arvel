"""Additional QueryBuilder coverage — secondary chainables and terminal ops."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, UnknownRelationError
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class Bag(Model):
    __tablename__ = "bags_m"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(String(80), nullable=True, default=None)


async def _setup(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_or_where_filters_with_disjunction(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    await Bag.create(name="a", qty=1)
    await Bag.create(name="b", qty=2)
    await Bag.create(name="c", qty=3)
    rows = await Bag.or_where(name="a", qty=3).order_by("name").all()
    assert [r.name for r in rows] == ["a", "c"]


async def test_or_where_with_no_args_returns_clone(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    await Bag.create(name="a", qty=1)
    rows = await Bag.or_where().all()
    assert len(rows) == 1


async def test_where_between_and_not_between(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    for i in range(1, 6):
        await Bag.create(name=f"b{i}", qty=i)
    inside = await Bag.where_between("qty", 2, 4).order_by("qty").all()
    outside = await Bag.where_not_between("qty", 2, 4).order_by("qty").all()
    assert [r.qty for r in inside] == [2, 3, 4]
    assert [r.qty for r in outside] == [1, 5]


async def test_where_null_and_not_null(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    await Bag.create(name="with", qty=0, note="hi")
    await Bag.create(name="without", qty=0, note=None)
    nulls = await Bag.where_null("note").all()
    fulls = await Bag.where_not_null("note").all()
    assert [r.name for r in nulls] == ["without"]
    assert [r.name for r in fulls] == ["with"]


async def test_where_not_in_filters(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    for name in ["a", "b", "c"]:
        await Bag.create(name=name, qty=0)
    rows = await Bag.where_not_in("name", ["b"]).order_by("name").all()
    assert [r.name for r in rows] == ["a", "c"]


async def test_latest_and_oldest(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    for i in range(3):
        await Bag.create(name=f"x{i}", qty=i)
    latest = await Bag.latest("qty").first()
    oldest = await Bag.oldest("qty").first()
    assert latest is not None
    assert oldest is not None
    assert latest.qty == 2
    assert oldest.qty == 0


async def test_group_by_and_having_compile(engine: Any, session: AsyncSession) -> None:
    from sqlalchemy import func

    await _setup(engine)
    for i in range(3):
        await Bag.create(name="dup", qty=i)
    qb = Bag.group_by("name").having(func.count(Bag.id) > 2)
    # We don't run the query — group_by + having should compile.
    compiled = qb._stmt.compile(dialect=engine.dialect)  # pyright: ignore[reportPrivateUsage]  # test compiles the private SQL stmt directly
    assert "GROUP BY" in str(compiled).upper()
    assert "HAVING" in str(compiled).upper()


async def test_distinct_chainable(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    await Bag.create(name="d", qty=1)
    qb = Bag.distinct()
    compiled = qb._stmt.compile(dialect=engine.dialect)  # pyright: ignore[reportPrivateUsage]  # test compiles the private SQL stmt directly
    assert "DISTINCT" in str(compiled).upper()


async def test_value_returns_single_scalar(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    await Bag.create(name="solo", qty=42)
    val = await Bag.value("qty")
    assert val == 42


async def test_get_is_alias_for_all(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    await Bag.create(name="a", qty=1)
    await Bag.create(name="b", qty=2)
    rows = await Bag.get()
    assert len(rows) == 2


async def test_each_iterates_one_by_one(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    for i in range(5):
        await Bag.create(name=f"e{i}", qty=i)
    seen: list[int] = []

    async def visit(bag: Bag) -> None:
        seen.append(bag.qty)

    await Bag.order_by("qty").each(visit)
    assert seen == [0, 1, 2, 3, 4]


async def test_with_unknown_relation_raises(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    with pytest.raises(UnknownRelationError):
        Bag.with_("not_a_relation")


async def test_find_via_query_builder(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    bag = await Bag.create(name="findable", qty=1)
    found = await Bag.find(bag.id)
    assert found is not None
    assert found.name == "findable"


async def test_find_or_fail_via_query_builder_raises(engine: Any, session: AsyncSession) -> None:
    from arvel.database import ModelNotFoundError

    await _setup(engine)
    with pytest.raises(ModelNotFoundError):
        await Bag.find_or_fail(9999)


async def test_when_otherwise_applies_fallback(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    await Bag.create(name="low", qty=1)
    await Bag.create(name="high", qty=10)

    rows = (
        await Bag.query()
        .when(
            False,
            lambda query: query.where(Bag.qty >= 10),
            otherwise=lambda query: query.where(Bag.qty < 10),
        )
        .all()
    )

    assert [row.name for row in rows] == ["low"]


async def test_shared_lock_first_and_sole(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    await Bag.create(name="solo", qty=1)

    first = await Bag.where(Bag.name == "solo").shared_lock().first()
    sole = await Bag.where(Bag.name == "solo").shared_lock().sole()

    assert first is not None
    assert first.name == "solo"
    assert sole.name == "solo"


async def test_update_or_create_updates_existing_model(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)

    created = await Bag.query().update_or_create({"name": "upserted"}, {"qty": 1})
    updated = await Bag.query().update_or_create({"name": "upserted"}, {"qty": 7})

    assert updated.id == created.id
    assert updated.qty == 7
    refreshed = await Bag.find(created.id)
    assert refreshed is not None
    assert refreshed.qty == 7
