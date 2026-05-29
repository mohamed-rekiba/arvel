"""Create the ``cart_items`` table (BIGSERIAL PK, UUID FK to carts/products)."""

from __future__ import annotations

from arvel.database import Blueprint, Schema

__tablename__ = "cart_items"


async def up(schema: Schema) -> None:
    def _table(t: Blueprint) -> None:
        t.id()
        t.uuid("cart_id").nullable(value=False).constrained("carts").cascade_on_delete()
        t.uuid("product_id").nullable(value=False).constrained("products").cascade_on_delete()
        t.integer("quantity").default(1).nullable(value=False)
        t.decimal("unit_price_snapshot", precision=10, scale=2).nullable(value=False)
        t.timestamps()
        t.unique(["cart_id", "product_id"], name="cart_items_cart_product_unique")
        t.index(["cart_id"], name="cart_items_cart_id_idx")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    schema.drop_if_exists(__tablename__)
