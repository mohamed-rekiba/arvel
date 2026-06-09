"""Product resource — transforms a product row into the admin API shape.

Accepts either the writable ``Product`` or the read-only ``ProductCatalog``
view: admin list reads the view (for ``real_status``), while create/update/
lifecycle paths hold a ``Product``. ``deleted_at`` and ``real_status`` only
exist on one side each, so they're read defensively.
"""

from __future__ import annotations

from typing import Any

from app.models.product import Product
from app.models.product_catalog import ProductCatalog
from arvel.http.resources import JsonResource


class ProductResource(JsonResource[Product | ProductCatalog]):
    def to_dict(self, request: Any) -> dict[str, Any]:
        p = self.resource
        deleted_at = getattr(p, "deleted_at", None)
        real_status: str | None = getattr(p, "real_status", None)
        return {
            "id": str(p.id),
            "name": p.name or {},
            "slug": p.slug or {},
            "description": p.description or {},
            "price": float(p.price or 0),
            "stock_qty": int(p.stock_qty or 0),
            "status": p.status or "draft",
            "real_status": real_status,
            "published_at": p.published_at.isoformat() if p.published_at else None,
            "category_id": str(p.category_id or ""),
            "vendor_id": str(p.vendor_id or ""),
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            "deleted_at": deleted_at.isoformat() if deleted_at else None,
        }
