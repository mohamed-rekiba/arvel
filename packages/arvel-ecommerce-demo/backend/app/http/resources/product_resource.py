"""Product resource — transforms a Product model for API responses."""

from __future__ import annotations

from typing import Any

from app.models.product import Product
from arvel.http.resources import JsonResource


class ProductResource(JsonResource[Product]):
    def to_dict(self, _request: Any) -> dict[str, Any]:
        p = self.resource
        return {
            "id": str(p.id),
            "name": p.name,
            "slug": p.slug,
            "description": p.description,
            "price": float(p.price) if p.price is not None else None,
            "stock_qty": p.stock_qty,
            "status": p.status,
            "published_at": p.published_at.isoformat() if p.published_at else None,
            "deleted_at": p.deleted_at.isoformat() if p.deleted_at else None,
        }
