"""Create the ``order_items`` table (BIGSERIAL PK, UUID FKs to orders/products)."""

from __future__ import annotations

from arvel.database import Blueprint, Schema

__tablename__ = "order_items"


async def up(schema: Schema) -> None:
    def _table(t: Blueprint) -> None:
        t.id()
        t.uuid("order_id").nullable(value=False).constrained("orders").cascade_on_delete()
        # Nullable + SET NULL: a product can be force-deleted after the order is
        # placed; the line keeps product_name_snapshot so history stays readable.
        t.uuid("product_id").nullable().constrained("products").null_on_delete()
        t.string("product_name_snapshot", length=300).nullable(value=False)
        t.integer("quantity").nullable(value=False)
        t.decimal("unit_price", precision=10, scale=2).nullable(value=False)
        t.decimal("subtotal", precision=10, scale=2).nullable(value=False)
        t.timestamps()
        t.index(["order_id"], name="order_items_order_id_idx")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    schema.drop_if_exists(__tablename__)
