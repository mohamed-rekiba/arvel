"""Order model — created at checkout, immutable after placement."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from arvel.database import (
    Model,
    SoftDeletes,
    Timestamps,
    decimal,
    enum,
    foreign_id,
    jsonb,
    text,
    uuid_id,
)

if TYPE_CHECKING:
    from arvel.database import BelongsTo, HasMany

    from app.models.order_item import OrderItem
    from app.models.user import User

_ORDER_STATUSES = ("pending", "confirmed", "processing", "shipped", "delivered", "cancelled")


class Order(Model, Timestamps, SoftDeletes):
    __tablename__ = "orders"

    id: uuid.UUID = uuid_id()
    user_id: int = foreign_id("users.id")
    status: str = enum(_ORDER_STATUSES, name="orders_status", default="pending")
    total: Decimal = decimal(10, 2, default=Decimal(0))
    shipping_address: Any = jsonb(default=dict)
    note: str | None = text(nullable=True, default=None)

    def items(self) -> HasMany[OrderItem]:
        return self.has_many("OrderItem", foreign_key="order_id")

    def user(self) -> BelongsTo[User]:
        return self.belongs_to("User", foreign_key="user_id")


__all__ = ["Order"]
