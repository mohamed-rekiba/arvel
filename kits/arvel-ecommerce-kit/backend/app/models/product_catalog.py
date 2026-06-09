"""ProductCatalog — read-only ORM model backed by the products_catalog materialized view."""

from __future__ import annotations

from datetime import UTC, timedelta
from datetime import datetime as _datetime
from typing import Any

from arvel.config import config
from arvel.database import QueryBuilder, ViewModel, datetime, jsonb, string, uuid
from arvel.database.attributes import accessor

from app.models.product_base import ProductBase


class ProductCatalog(ProductBase, ViewModel):
    """Full product catalog view — all non-deleted products with computed real_status.

    Backed by the ``products_catalog`` materialized view. Write operations raise
    ``ReadOnlyModelError`` — use ``Product`` for mutations.

    Storefront queries use the ``visible`` scope (``ProductCatalog.visible()``).
    Admin queries use the full table and filter by ``status`` / ``real_status`` as needed.

    ``__morph_class__`` makes this view present as ``"Product"`` for polymorphic
    lookups, so ``get_media()`` / ``.with_("media")`` transparently share Product's
    media rows instead of looking for ``"ProductCatalog"`` rows that never exist.

    """

    __morph_class__: str = "Product"

    __tablename__ = "products_catalog"
    __is_materialized_view__ = True

    # real_status is computed by the view's CASE expression; not on the products table.
    real_status: str = string()

    # View-specific: denormalised category hierarchy.
    category_name: dict[str, Any | None] = jsonb(nullable=True, default=None)
    category_slug: dict[str, Any | None] = jsonb(nullable=True, default=None)
    # Plain nullable UUID — a denormalised FK reference, not a relational constraint.
    category_parent_id: str | None = uuid(nullable=True, default=None)
    parent_category_name: dict[str, Any | None] = jsonb(nullable=True, default=None)
    parent_category_slug: dict[str, Any | None] = jsonb(nullable=True, default=None)
    # Storefront-visible description (denormalised from products).
    description: dict[str, Any | None] = jsonb(nullable=True, default=None)
    # View-specific: denormalised vendor info.
    vendor_name: str | None = string(nullable=True, default=None)
    vendor_slug: str | None = string(nullable=True, default=None)
    # Timestamps are non-nullable on the products table; the view exposes them as
    # nullable because a LEFT JOIN can yield NULLs in unusual edge cases.
    created_at: _datetime | None = datetime(nullable=True, default=None)
    updated_at: _datetime | None = datetime(nullable=True, default=None)

    def scope_visible(self, query: QueryBuilder[ProductCatalog]) -> QueryBuilder[ProductCatalog]:
        # "visible" = published and neither soft-deleted nor in a draft/hidden state;
        # the view's CASE expression folds all of that into real_status.
        return query.where(ProductCatalog.real_status == "visible")

    @accessor
    def is_new(self) -> bool:
        # Wears the "new" badge for catalog.new_product_days after creation.
        # The view exposes created_at as nullable, and a LEFT JOIN can hand back a
        # tz-naive value, so normalize before comparing.
        created = self.created_at
        if created is None:
            return False
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        window = timedelta(days=int(config("catalog.new_product_days", 30)))
        return (_datetime.now(UTC) - created) <= window


__all__ = ["ProductCatalog"]
