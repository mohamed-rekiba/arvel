"""Category model — hierarchical product taxonomy."""

from __future__ import annotations

import uuid
from datetime import datetime as _datetime
from typing import TYPE_CHECKING, Any

from arvel.database import (
    Model,
    SoftDeletes,
    Timestamps,
    TranslatableMixin,
    enum,
    foreign_uuid,
    jsonb,
    uuid_id,
)

if TYPE_CHECKING:
    from arvel.database import BelongsTo, HasMany

    from app.models.product_catalog import ProductCatalog


class Category(TranslatableMixin, Model, Timestamps, SoftDeletes):
    __tablename__ = "categories"

    id: uuid.UUID = uuid_id()
    name: Any = jsonb(default=dict)
    slug: Any = jsonb(default=dict)
    status: str = enum(["draft", "published"], name="categories_status", default="published")
    published_at: _datetime | None = None
    parent_id: uuid.UUID | None = foreign_uuid("categories.id", nullable=True)

    def catalog_products(self) -> HasMany[ProductCatalog]:
        return self.has_many("ProductCatalog", foreign_key="category_id")

    # Self-referential taxonomy.
    def children(self) -> HasMany[Category]:
        return self.has_many("Category", foreign_key="parent_id")

    def parent(self) -> BelongsTo[Category]:
        return self.belongs_to("Category", foreign_key="parent_id")


__all__ = ["Category"]
