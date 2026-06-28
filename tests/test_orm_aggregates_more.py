"""ORM (doc 07) — with_avg / with_exists + latest / oldest helpers."""

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


async def test_with_avg() -> None:
    db = await _setup()
    try:
        shop = await Shop.create(name="A")
        await Item.create(shop_id=shop.id, price=10)
        await Item.create(shop_id=shop.id, price=20)
        rows = await Shop.with_avg("items", "price").get()
        assert rows[0].items_avg == 15
    finally:
        await db.dispose()


async def test_with_exists() -> None:
    db = await _setup()
    try:
        stocked = await Shop.create(name="Stocked")
        empty = await Shop.create(name="Empty")
        await Item.create(shop_id=stocked.id, price=5)
        by_id = {s.id: s for s in await Shop.with_exists("items").get()}
        assert by_id[stocked.id].items_exists
        assert not by_id[empty.id].items_exists
    finally:
        await db.dispose()


async def test_latest_and_oldest() -> None:
    db = await _setup()
    try:
        shop = await Shop.create(name="A")
        await Item.create(shop_id=shop.id, price=10)
        await Item.create(shop_id=shop.id, price=30)
        await Item.create(shop_id=shop.id, price=20)
        newest = await Item.latest("price").get()
        oldest = await Item.oldest("price").get()
        assert [r.price for r in newest] == [30, 20, 10]
        assert [r.price for r in oldest] == [10, 20, 30]
    finally:
        await db.dispose()
