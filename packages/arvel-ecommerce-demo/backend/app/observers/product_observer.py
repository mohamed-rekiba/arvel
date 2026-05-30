"""Product lifecycle observer."""

from __future__ import annotations

from datetime import UTC, datetime

from arvel.database.events import Observer

from app.models.product import Product


class ProductObserver(Observer[Product]):
    def __init__(self) -> None:
        pass

    def saving(self, product: Product) -> None:
        if product.status == "published" and product.published_at is None:
            product.published_at = datetime.now(UTC)


__all__ = ["ProductObserver"]
