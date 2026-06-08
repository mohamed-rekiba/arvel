"""Eloquent-parity: where(col, value) and where(col, operator, value) string forms."""

from __future__ import annotations

import pytest
from arvel.database import Model, id_, integer, string
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class Person(Model):
    __tablename__ = "where_str_people"
    id: int = id_()
    email: str = string(120, default="")
    age: int = integer(default=0)


async def _seed(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    await Person.create(email="john@example.com", age=30)
    await Person.create(email="jane@example.com", age=25)
    await Person.create(email="JOHN@EXAMPLE.COM", age=40)


async def test_where_column_value_implicit_equals(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _seed(engine)
    rows = await Person.where("email", "john@example.com").get()
    assert [r.age for r in rows] == [30]


async def test_where_column_operator_value(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await Person.where("email", "ilike", "john@example.com").order_by("age").get()
    # ilike is case-insensitive → matches both the lower and upper rows.
    assert sorted(r.age for r in rows) == [30, 40]


async def test_where_comparison_operator(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await Person.where("age", ">=", 30).order_by("age").get()
    assert [r.age for r in rows] == [30, 40]


async def test_where_string_form_chains_as_and(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _seed(engine)
    rows = (
        await Person.where("email", "ilike", "%example.com")
        .where("age", "<", 35)
        .order_by("age")
        .get()
    )
    # Both john (30) and jane (25) match the domain and the age bound.
    assert [r.age for r in rows] == [25, 30]


async def test_or_where_string_form(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await Person.where("age", 30).or_where("age", 25).order_by("age").get()
    assert [r.age for r in rows] == [25, 30]


async def test_where_unknown_operator_raises(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    with pytest.raises(ValueError, match="Unsupported operator"):
        Person.where("email", "matches", "x")


async def test_where_single_string_raises(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    with pytest.raises(TypeError, match="where\\(column, value\\)"):
        Person.where("email")


async def test_where_expression_form_unaffected(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _seed(engine)
    rows = await Person.where(Person.age == 25).get()
    assert [r.email for r in rows] == ["jane@example.com"]
