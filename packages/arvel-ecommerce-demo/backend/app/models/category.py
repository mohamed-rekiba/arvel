"""Category model — hierarchical product taxonomy."""

from __future__ import annotations

import uuid
from datetime import datetime as _datetime
from typing import Any

from arvel.database import (
    Model,
    SoftDeletes,
    Timestamps,
    TranslatableMixin,
    datetime,
    enum,
    foreign_uuid,
    has_many_attr,
    jsonb,
    uuid_id,
)


class Category(TranslatableMixin, Model, Timestamps, SoftDeletes):
    __tablename__ = "categories"

    id: uuid.UUID = uuid_id()
    name: Any = jsonb(default=dict)
    slug: Any = jsonb(default=dict)
    status: str = enum(["draft", "published"], name="categories_status", default="published")
    published_at: _datetime | None = datetime(nullable=True, default=None)
    parent_id: uuid.UUID | None = foreign_uuid("categories.id", nullable=True)
    catalog_products: list[Any] = has_many_attr("ProductCatalog", fk="category_id")


__all__ = ["Category"]
