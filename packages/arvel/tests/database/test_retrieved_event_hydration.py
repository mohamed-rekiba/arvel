"""The retrieved event fires on every hydration path, not just find().

Eloquent fires `retrieved` whenever a model is pulled from the DB — first, get,
all, sole, and paginate included.
"""

from __future__ import annotations

from typing import Any

from arvel.database import Model, Observer
from arvel.database.events import clear_observers
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class RevTag(Model):
    __tablename__ = "rev_tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))


class Counter(Observer[RevTag]):
    def __init__(self) -> None:
        self.count = 0

    def retrieved(self, instance: RevTag) -> None:
        self.count += 1


async def _setup(engine: AsyncEngine) -> Counter:
    clear_observers(RevTag)
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    counter = Counter()
    RevTag.observe(counter)
    return counter


async def test_retrieved_fires_on_first(engine: AsyncEngine, session: AsyncSession) -> None:
    counter = await _setup(engine)
    await RevTag.create(name="a")
    counter.count = 0
    await RevTag.query().first()
    assert counter.count == 1


async def test_retrieved_fires_once_per_row_on_all(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    counter = await _setup(engine)
    await RevTag.create(name="a")
    await RevTag.create(name="b")
    counter.count = 0
    rows: Any = await RevTag.query().all()
    assert len(rows) == 2
    assert counter.count == 2


async def test_retrieved_fires_on_paginate(engine: AsyncEngine, session: AsyncSession) -> None:
    counter = await _setup(engine)
    await RevTag.create(name="a")
    await RevTag.create(name="b")
    counter.count = 0
    await RevTag.query().paginate(per_page=10)
    assert counter.count == 2


async def test_retrieved_fires_once_on_find(engine: AsyncEngine, session: AsyncSession) -> None:
    counter = await _setup(engine)
    tag = await RevTag.create(name="a")
    counter.count = 0
    await RevTag.find(tag.id)
    assert counter.count == 1
