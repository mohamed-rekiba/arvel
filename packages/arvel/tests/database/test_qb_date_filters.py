"""Eloquent-parity: date/time WHERE helpers."""

from __future__ import annotations

import datetime

from arvel.database import Model, column, id_, string
from sqlalchemy import DateTime
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class Event(Model):
    __tablename__ = "date_events"
    id: int = id_()
    name: str = string(20, default="")
    at: datetime.datetime = column(
        DateTime, default=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    )


async def _seed(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    utc = datetime.UTC
    await Event.create(name="a", at=datetime.datetime(2026, 5, 30, 14, 5, 9, tzinfo=utc))
    await Event.create(name="b", at=datetime.datetime(2025, 1, 2, 3, 4, 5, tzinfo=utc))
    await Event.create(name="c", at=datetime.datetime(2026, 12, 30, 14, 0, 0, tzinfo=utc))


async def test_where_year(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await Event.where_year("at", 2026).order_by("name").all()
    assert [r.name for r in rows] == ["a", "c"]


async def test_where_month(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await Event.where_month("at", 5).all()
    assert [r.name for r in rows] == ["a"]


async def test_where_day(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await Event.where_day("at", 30).order_by("name").all()
    assert [r.name for r in rows] == ["a", "c"]


async def test_where_date_str(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await Event.where_date("at", "2026-05-30").all()
    assert [r.name for r in rows] == ["a"]


async def test_where_date_obj(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await Event.where_date("at", datetime.date(2025, 1, 2)).all()
    assert [r.name for r in rows] == ["b"]


async def test_where_time(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await Event.where_time("at", "14:05:09").all()
    assert [r.name for r in rows] == ["a"]


async def test_or_where_year_composes(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    # name == 'b' OR year == 2026  -> all three
    rows = await Event.where(name="b").or_where_year("at", 2026).order_by("name").all()
    assert [r.name for r in rows] == ["a", "b", "c"]


async def test_where_year_then_month_ands(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await Event.where_year("at", 2026).where_month("at", 12).all()
    assert [r.name for r in rows] == ["c"]
