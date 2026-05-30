"""Order model — created at checkout, immutable after placement."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from arvel.database import (
    Model,
    SoftDeletes,
    Timestamps,
    decimal,
    enum,
    foreign_id,
    has_many_attr,
    jsonb,
    text,
    uuid_id,
)

_ORDER_STATUSES = ("pending", "confirmed", "processing", "shipped", "delivered", "cancelled")


class Order(Model, Timestamps, SoftDeletes):
    __tablename__ = "orders"

    id: uuid.UUID = uuid_id()
    user_id: int = foreign_id("users.id")
    status: str = enum(_ORDER_STATUSES, name="orders_status", default="pending")
    total: Decimal = decimal(10, 2, default=Decimal(0))
    shipping_address: Any = jsonb(default=dict)
    note: str | None = text(nullable=True, default=None)
    items: list[Any] = has_many_attr("OrderItem", fk="order_id")


__all__ = ["Order"]
