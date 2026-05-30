"""Cart model — one per authenticated customer."""

from __future__ import annotations

import uuid
from datetime import UTC, timedelta
from datetime import datetime as dt

from arvel.database import Model, Prunable, Timestamps, foreign_id, uuid_id

_ABANDON_DAYS = 30


class Cart(Model, Timestamps, Prunable):
    __tablename__ = "carts"

    id: uuid.UUID = uuid_id()
    user_id: int = foreign_id("users.id")

    def prunable_query(self) -> object:  # type: ignore[override]
        # Prune carts that haven't been touched in 30 days.
        cutoff = dt.now(UTC) - timedelta(days=_ABANDON_DAYS)
        return Cart.query().where(Cart.updated_at < cutoff)


__all__ = ["Cart"]
