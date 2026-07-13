"""ORM depth (doc 07) — cursor()/lazy() streaming. Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Item(Model):
    __fields__ = {"n": int}
    __fillable__ = ["n"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    Item.set_connection(db)
    await db.execute(sa.schema.CreateTable(Item.__table__))
    for i in range(5):
        await Item.create(n=i)
    return db


async def test_cursor_streams_models_one_at_a_time() -> None:
    db = await _setup()
    try:
        seen = [item.n async for item in Item.cursor()]
        assert sorted(seen) == [0, 1, 2, 3, 4]
    finally:
        await db.dispose()


async def test_cursor_respects_where() -> None:
    db = await _setup()
    try:
        seen = [item.n async for item in Item.where("n", ">", 2).cursor()]
        assert sorted(seen) == [3, 4]
    finally:
        await db.dispose()


async def test_lazy_streams_models() -> None:
    db = await _setup()
    try:
        count = 0
        async for item in Item.lazy():
            assert isinstance(item, Item)
            count += 1
        assert count == 5
    finally:
        await db.dispose()
