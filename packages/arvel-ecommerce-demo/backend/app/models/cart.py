"""Cart model — one per authenticated customer."""

from __future__ import annotations

import uuid
from datetime import UTC, timedelta
from datetime import datetime as dt
from typing import TYPE_CHECKING

from arvel.database import Model, Prunable, Timestamps, foreign_id, uuid_id

if TYPE_CHECKING:
    from arvel.database import HasMany

    from app.models.cart_item import CartItem

_ABANDON_DAYS = 30


class Cart(Model, Timestamps, Prunable):
    __tablename__ = "carts"

    id: uuid.UUID = uuid_id()
    user_id: int = foreign_id("users.id")

    def items(self) -> HasMany[CartItem]:
        return self.has_many("CartItem", foreign_key="cart_id")

    def prunable_query(self) -> object:  # type: ignore[override]
        # Prune carts that haven't been touched in 30 days.
        cutoff = dt.now(UTC) - timedelta(days=_ABANDON_DAYS)
        return Cart.where(Cart.updated_at < cutoff)


__all__ = ["Cart"]
