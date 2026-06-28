"""ORM depth (doc 07) — upsert (insert-or-update on conflict). Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Product(Model):
    __fields__ = {"sku": str, "price": int}
    __fillable__ = ["sku", "price"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    Product.set_connection(db)
    await db.execute(sa.schema.CreateTable(Product.__table__))
    await db.statement("CREATE UNIQUE INDEX ux_products_sku ON products (sku)")
    return db


async def test_upsert_inserts_then_updates_on_conflict() -> None:
    db = await _setup()
    try:
        await Product.upsert(
            [{"sku": "A", "price": 10}, {"sku": "B", "price": 20}], ["sku"], ["price"]
        )
        assert len(await Product.all()) == 2

        # conflict on sku=A → update price, not a duplicate row
        await Product.upsert([{"sku": "A", "price": 99}], ["sku"], ["price"])
        assert len(await Product.all()) == 2
        a = await Product.where(sku="A").first()
        assert a.price == 99
    finally:
        await db.dispose()


async def test_upsert_defaults_update_columns() -> None:
    db = await _setup()
    try:
        await Product.upsert([{"sku": "C", "price": 5}], ["sku"])
        await Product.upsert([{"sku": "C", "price": 7}], ["sku"])  # no explicit update cols
        c = await Product.where(sku="C").first()
        assert c.price == 7
    finally:
        await db.dispose()
