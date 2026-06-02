"""Product — the writable catalog entity backed by the products table."""

from __future__ import annotations

from arvel.database import Model, QueryBuilder, SoftDeletes, Timestamps, enum

from app.models.product_base import IMAGES_COLLECTION, ProductBase


class Product(
    ProductBase,
    Model,
    Timestamps,
    SoftDeletes,
):
    """E-commerce product with i18n name/slug/description and polymorphic images."""

    __tablename__ = "products"

    # Override ProductBase.status with the Enum-typed column for the writable table.
    status: str = enum(["draft", "published"], name="products_status", default="draft")

    def scope_published(self, query: QueryBuilder[Product]) -> QueryBuilder[Product]:
        return query.where(Product.status == "published").where_not_null(Product.published_at)

    def scope_draft(self, query: QueryBuilder[Product]) -> QueryBuilder[Product]:
        return query.where(Product.status == "draft")


__all__ = ["IMAGES_COLLECTION", "Product"]
