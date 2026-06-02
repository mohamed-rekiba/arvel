"""ProductBase — shared foundation for Product and ProductCatalog.

``ProductMediaMixin`` — HasMedia subclass with the catalog image-conversion config.
``ProductBase`` — Abstract SQLAlchemy mixin: every column, relation, cast, and
                         behaviour shared between the writable ``Product`` table model
                         and the read-only ``ProductCatalog`` view model.

Columns NOT declared here and why:
  ``created_at`` / ``updated_at`` Product inherits these via ``Timestamps``; declaring
                                   them here would create a duplicate-column conflict.
                                   PublishedProduct declares them directly (nullable,
                                   because the view JOIN can yield NULLs).

  ``status`` ``@declared_attr`` maps to a generic string column; ``Product``
                           overrides with the Enum-typed ``enum()`` column. The view exposes
                           the raw ``p.status`` value from the ``products`` table.

Mutations (save / create / delete) are intentionally absent from ``ProductBase``:
``ProductCatalog`` is read-only via ``ViewModel`` — those methods raise
``ReadOnlyModelError``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, ClassVar

from arvel.database import (
    column_attr,
    datetime,
    decimal,
    foreign,
    foreign_uuid,
    integer,
    jsonb,
    relationship,
    string,
    tsvector,
    uuid_id,
)
from arvel_image import Conversion, HasMedia, MediaCollection
from sqlalchemy.orm import MappedAsDataclass

from app.models.base import TranslatableMixin
from app.models.category import Category
from app.models.vendor import Vendor

IMAGES_COLLECTION = "images"


class ProductMediaMixin(HasMedia):
    """HasMedia subclass that registers the three standard product image conversions."""

    def register_media_collections(self) -> None:
        (
            MediaCollection(IMAGES_COLLECTION)
            .with_conversions(
                Conversion("thumbnail").fit("cover", 150, 150).quality(85),
                Conversion("card").fit("cover", 400, 300).quality(85),
                Conversion("full").fit("contain", 1200, 900).quality(90),
            )
            .register_on(self)
        )


class ProductBase(ProductMediaMixin, TranslatableMixin, MappedAsDataclass):
    """Abstract base for Product and PublishedProduct.


    Uses ``declared_attr`` so each concrete mapper gets its own Column /
    Relationship instance while the declaration lives once. Extends
    ``MappedAsDataclass`` so SQLAlchemy treats it as a typed-dataclass mixin —
    required once the concrete models (``Product``, ``ProductCatalog``) are
    dataclass-mapped, enforced in SQLA 2.1.
    """

    __abstract__ = True

    __casts__: ClassVar[dict[str, str]] = {
        "name": "dict",
        "slug": "dict",
        "description": "dict",
        "stock_qty": "int",
    }

    # ── shared columns ────────────────────────────────────────────────────────

    @column_attr
    def id(self) -> uuid.UUID:
        return uuid_id()

    @column_attr
    def name(self) -> dict[str, Any]:
        return jsonb(default=dict)

    @column_attr
    def slug(self) -> dict[str, Any]:
        return jsonb(default=dict)

    @column_attr
    def description(self) -> dict[str, Any] | None:
        # Non-nullable on the products table (DB constraint), nullable in the view.
        return jsonb(nullable=True, default=dict)

    @column_attr
    def price(self) -> Decimal | None:
        return decimal(10, 2, nullable=True, default=None)

    @column_attr
    def stock_qty(self) -> int:
        return integer(default=0)

    @column_attr
    def search_vector(self) -> str | None:
        return tsvector()

    @column_attr
    def category_id(self) -> uuid.UUID | None:
        return foreign_uuid("categories.id", nullable=True)

    @column_attr
    def vendor_id(self) -> uuid.UUID | None:
        return foreign_uuid("vendors.id", nullable=True)

    @column_attr
    def published_at(self) -> Any:
        return datetime(nullable=True, default=None)

    # ── shared relations ──────────────────────────────────────────────────────

    @column_attr
    def category(self) -> Category | None:
        klass = self
        return relationship(
            "Category",
            primaryjoin=lambda: foreign(klass.category_id) == Category.id,
            init=False,
            viewonly=True,
        )

    @column_attr
    def vendor(self) -> Vendor | None:
        klass = self
        return relationship(
            "Vendor",
            primaryjoin=lambda: foreign(klass.vendor_id) == Vendor.id,
            init=False,
            viewonly=True,
        )

    # ── status ────────────────────────────────────────────────────────────────

    @column_attr
    def status(self) -> str:
        # Generic string mapping for ProductCatalog (view column).
        # Product overrides this with the Enum-typed enum() column.
        return string(50, nullable=False, default="draft")


__all__ = ["IMAGES_COLLECTION", "ProductBase", "ProductMediaMixin"]
