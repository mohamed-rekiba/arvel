"""Category resource — transforms a Category model for API responses."""

from __future__ import annotations

from typing import Any

from app.models.category import Category
from arvel.http.resources import JsonResource


class CategoryResource(JsonResource[Category]):
    def to_dict(self, _request: Any) -> dict[str, Any]:
        c = self.resource
        return {
            "id": str(c.id),
            "name": c.name,
            "slug": c.slug or {},
            "status": c.status,
            "published_at": c.published_at.isoformat() if c.published_at else None,
            "parent_id": str(c.parent_id) if c.parent_id else None,
            "deleted_at": c.deleted_at.isoformat() if c.deleted_at else None,
        }
