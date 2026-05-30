"""CartItem model — one line per product in the cart."""

from __future__ import annotations

import uuid
from decimal import Decimal

from arvel.database import Model, Timestamps, decimal, foreign_uuid, id_, integer


class CartItem(Model, Timestamps):
    __tablename__ = "cart_items"

    id: int = id_()
    cart_id: uuid.UUID = foreign_uuid("carts.id", on_delete="CASCADE")
    product_id: uuid.UUID = foreign_uuid("products.id", on_delete="CASCADE")
    quantity: int = integer(default=1)
    unit_price_snapshot: Decimal = decimal(10, 2, default=Decimal(0))


__all__ = ["CartItem"]
