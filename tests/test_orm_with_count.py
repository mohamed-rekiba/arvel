"""ORM (doc 07) — relationship aggregates: with_count / with_sum. Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Shop(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def items(self) -> object:
        return self.has_many(Item)


class Item(Model):
    __fields__ = {"shop_id": int, "price": int}
    __fillable__ = ["shop_id", "price"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Shop, Item):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_with_count_adds_relation_count() -> None:
    db = await _setup()
    try:
        stocked = await Shop.create(name="Stocked")
        empty = await Shop.create(name="Empty")
        await Item.create(shop_id=stocked.id, price=10)
        await Item.create(shop_id=stocked.id, price=5)

        by_id = {s.id: s for s in await Shop.with_count("items").get()}
        assert by_id[stocked.id].items_count == 2
        assert by_id[empty.id].items_count == 0  # COALESCE to 0, not NULL
    finally:
        await db.dispose()


async def test_with_sum_adds_relation_sum() -> None:
    db = await _setup()
    try:
        stocked = await Shop.create(name="Stocked")
        empty = await Shop.create(name="Empty")
        await Item.create(shop_id=stocked.id, price=10)
        await Item.create(shop_id=stocked.id, price=5)

        by_id = {s.id: s for s in await Shop.with_sum("items", "price").get()}
        assert by_id[stocked.id].items_sum == 15
        assert by_id[empty.id].items_sum == 0
    finally:
        await db.dispose()
