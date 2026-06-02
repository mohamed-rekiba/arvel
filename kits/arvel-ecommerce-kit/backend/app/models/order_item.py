"""OrderItem — line item within an order, with price and name snapshots."""

from __future__ import annotations

import uuid
from decimal import Decimal

from arvel.database import Model, Timestamps, decimal, foreign_uuid, id_, string


class OrderItem(Model, Timestamps):
    __tablename__ = "order_items"

    id: int = id_()
    order_id: uuid.UUID = foreign_uuid("orders.id", on_delete="CASCADE")
    product_id: uuid.UUID | None = foreign_uuid("products.id", on_delete="SET NULL", nullable=True)
    product_name_snapshot: str = string(300, default="")
    quantity: int = 0
    unit_price: Decimal = decimal(10, 2, default=Decimal(0))
    subtotal: Decimal = decimal(10, 2, default=Decimal(0))


__all__ = ["OrderItem"]
