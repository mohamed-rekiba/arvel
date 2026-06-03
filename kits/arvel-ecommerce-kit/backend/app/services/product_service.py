"""ProductService — all product-level DB operations.

Storefront reads use ProductCatalog ViewModel filtered to real_status='visible'.
Admin CRUD uses Product ORM directly; admin list uses ProductCatalog so real_status
is available without a join.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, TypedDict

from arvel.database import TranslatableMixin
from arvel.database.exceptions import InvalidCursorError
from arvel.logging.facade import Log
from arvel_image import Media

from app.models.product import Product
from app.models.product_base import IMAGES_COLLECTION
from app.models.product_catalog import ProductCatalog
from app.support.labels import label
from app.support.products_catalog import refresh_products_catalog


class ProductAdminFilter(TypedDict, total=False):
    trashed: str
    status: str | None
    real_status: str | None
    slug: str | None
    limit: int
    offset: int


class ProductNotFoundError(Exception):
    pass


class InsufficientStockError(Exception):
    pass


class ProductService:
    # ─── storefront ──────────────────────────────────────────────────────────

    async def list_published(
        self,
        *,
        locale: str = "en",
        limit: int = 20,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return await self._list_published(locale=locale, limit=limit, cursor=cursor)

    async def list_published_by_category_slug(
        self,
        slug: str,
        *,
        locale: str = "en",
        limit: int = 20,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return await self._list_published(
            locale=locale,
            limit=limit,
            cursor=cursor,
            category_slug=slug,
        )

    async def _list_published(
        self,
        *,
        locale: str,
        limit: int,
        cursor: str | None,
        category_slug: str | None = None,
    ) -> dict[str, Any]:
        """Cursor-paginated storefront listing via ProductCatalog ORM."""
        # .with_("media") batches the per-product media into one extra query —
        # without it the listing is a textbook N+1 (one media fetch per row).
        query = ProductCatalog.where(ProductCatalog.real_status == "visible").with_("media")
        if category_slug is not None:
            query = query.where_json_path("category_slug", locale, category_slug)

        # Malformed cursor must not 500 the storefront — cursor_paginate
        # raises InvalidCursorError, so fall back to page one.
        try:
            page = await query.cursor_paginate(
                limit,
                cursor=cursor,
                keyset=["published_at DESC", "id ASC"],
            )
        except InvalidCursorError:
            page = await query.cursor_paginate(
                limit, cursor=None, keyset=["published_at DESC", "id ASC"]
            )

        return {
            "data": [await self.product_to_storefront_with_media(p, locale) for p in page.items],
            "pagination": {"next_cursor": page.next_cursor, "has_more": page.has_more},
        }

    async def get_published_by_slug(self, slug: str, locale: str = "en") -> dict[str, Any] | None:
        product = (
            await ProductCatalog.where(ProductCatalog.real_status == "visible")
            .where_json_path("slug", locale, slug)
            .with_("media")
            .first()
        )
        if product is None:
            return None
        return await self.product_to_storefront_with_media(product, locale)

    async def search_published(
        self,
        *,
        q: str,
        locale: str = "en",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        sv = ProductCatalog.search_vector
        products: list[ProductCatalog] = (
            await ProductCatalog.where(ProductCatalog.real_status == "visible")
            .where_full_text(sv, q, tsquery_fn="plainto_tsquery", lang="simple")
            .order_by_relevance(sv, q, lang="simple")
            .with_("media")
            .limit(limit)
            .all()
        )
        return [await self.product_to_storefront_with_media(p, locale) for p in products]

    # ─── admin list / get ─────────────────────────────────────────────────────

    async def admin_list(self, *, filters: ProductAdminFilter | None = None) -> dict[str, Any]:
        f: ProductAdminFilter = filters or {}
        trashed = f.get("trashed", "without")
        status = f.get("status")
        real_status = f.get("real_status")
        slug = f.get("slug")
        limit = f.get("limit", 50)
        offset = f.get("offset", 0)

        if trashed == "without":
            # ProductCatalog has real_status; use it for all non-trashed reads.
            qb = ProductCatalog.query()
            if status:
                qb = qb.where(ProductCatalog.status == status)
            if real_status:
                qb = qb.where(ProductCatalog.real_status == real_status)
            if slug:
                qb = qb.where_json_path("slug", "en", slug)
            total: int = await qb.count()
            catalog_items: list[ProductCatalog] = (
                await qb.order_by("-created_at").limit(limit).offset(offset).all()
            )
            return {"data": [self._product_to_admin(p) for p in catalog_items], "total": total}

        if trashed == "only":
            qb_t = (
                Product.with_trashed()
                .with_("category", "vendor")
                .where_not_null(Product.deleted_at)
            )
        else:
            qb_t = Product.with_trashed().with_("category", "vendor")

        if status == "published":
            qb_t = qb_t.published()
        elif status == "draft":
            qb_t = qb_t.draft()
        elif status:
            qb_t = qb_t.where(Product.status == status)
        if slug:
            qb_t = qb_t.where_json_path("slug", "en", slug)

        total_t: int = await qb_t.count()
        trashed_items: list[Product] = (
            await qb_t.order_by("-created_at").limit(limit).offset(offset).all()
        )
        return {"data": [self._product_to_admin(p) for p in trashed_items], "total": total_t}

    async def admin_get(
        self, product_id: str, *, include_trashed: bool = False
    ) -> dict[str, Any] | None:
        try:
            pid = uuid.UUID(product_id)
        except ValueError:
            return None
        if include_trashed:
            product: Product | None = await Product.with_trashed().where(Product.id == pid).first()
        else:
            product = await Product.where(Product.id == pid).first()
        if product is None:
            return None
        return self._product_to_admin(product)

    # ─── admin catalog refresh ────────────────────────────────────────────────

    async def refresh_catalog(self) -> dict[str, Any]:
        """Manually refresh products_catalog and return the indexed count."""
        count = await refresh_products_catalog()
        return {
            "refreshed_at": datetime.now(UTC).isoformat(),
            "product_count": int(count),
        }

    # ─── admin create / update ────────────────────────────────────────────────

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        Log.debug("product.creating", name=label(data.get("name")))
        product: Product = await Product.create(
            name=data.get("name", {}),
            slug=data.get("slug", {}),
            description=data.get("description", {}),
            price=Decimal(str(data["price"])),
            stock_qty=data.get("stock_qty", 0),
            status="draft",
            category_id=uuid.UUID(str(data["category_id"])) if data.get("category_id") else None,
            vendor_id=uuid.UUID(str(data["vendor_id"])) if data.get("vendor_id") else None,
        )
        Log.debug("product.created", product_id=str(product.id))
        return self._product_to_admin(product)

    async def update(self, product_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        Log.debug("product.updating", product_id=product_id, fields=sorted(changes))
        pid = uuid.UUID(product_id)
        product: Product | None = await Product.with_trashed().where(Product.id == pid).first()
        if product is None:
            raise ProductNotFoundError(product_id)
        for key, val in changes.items():
            if key == "price":
                product.price = Decimal(str(val))
            elif key in {"category_id", "vendor_id"}:
                setattr(product, key, uuid.UUID(str(val)) if val else None)
            elif key in {"name", "slug", "description", "stock_qty", "status"}:
                setattr(product, key, val)
        await product.save()
        Log.debug("product.updated", product_id=product_id)
        return self._product_to_admin(product)

    # ─── admin lifecycle ──────────────────────────────────────────────────────

    async def soft_delete(self, product_id: str) -> None:
        Log.debug("product.deleting", product_id=product_id)
        pid = uuid.UUID(product_id)
        product: Product | None = await Product.where(Product.id == pid).first()
        if product is not None:
            await product.delete()
            Log.debug("product.deleted", product_id=product_id)

    async def force_delete(self, product_id: str) -> None:
        Log.debug("product.force_deleting", product_id=product_id)
        pid = uuid.UUID(product_id)
        product: Product | None = await Product.with_trashed().where(Product.id == pid).first()
        if product is not None:
            await product.force_delete()
            Log.debug("product.force_deleted", product_id=product_id)

    async def restore(self, product_id: str) -> dict[str, Any] | None:
        Log.debug("product.restoring", product_id=product_id)
        pid = uuid.UUID(product_id)
        product: Product | None = await Product.with_trashed().where(Product.id == pid).first()
        if product is None:
            return None
        await product.restore()
        Log.debug("product.restored", product_id=product_id)
        return self._product_to_admin(product)

    async def publish(self, product_id: str) -> dict[str, Any] | None:
        Log.debug("product.publishing", product_id=product_id)
        pid = uuid.UUID(product_id)
        product: Product | None = await Product.with_trashed().where(Product.id == pid).first()
        if product is None:
            return None
        product.status = "published"
        product.published_at = datetime.now(UTC)
        await product.save()
        Log.debug("product.published", product_id=product_id)
        return self._product_to_admin(product)

    async def unpublish(self, product_id: str) -> dict[str, Any] | None:
        Log.debug("product.unpublishing", product_id=product_id)
        pid = uuid.UUID(product_id)
        product: Product | None = await Product.with_trashed().where(Product.id == pid).first()
        if product is None:
            return None
        product.status = "draft"
        await product.save()
        Log.debug("product.unpublished", product_id=product_id)
        return self._product_to_admin(product)

    # ─── stock ────────────────────────────────────────────────────────────────

    async def get_stock(self, product_id: str) -> int:
        pid = uuid.UUID(product_id)
        product: Product | None = await Product.where(Product.id == pid).first()
        if product is None:
            raise ProductNotFoundError(product_id)
        return int(product.stock_qty)

    # ─── helpers ─────────────────────────────────────────────────────────────

    async def product_to_storefront_with_media(
        self, product: ProductCatalog, locale: str
    ) -> dict[str, Any]:
        media = await product.get_first_media(IMAGES_COLLECTION)
        image_payload = await self._image_payload(media)
        return self._product_to_storefront(product, locale, image_payload=image_payload)

    @classmethod
    async def _image_payload(cls, media: Media | None) -> dict[str, Any]:
        """Build the image payload for a storefront product card.

        Priority:
        1. Responsive srcset from the ``card`` conversion (width-optimised variants).
        2. Static width hints from conversion URLs if responsive wasn't generated.
        3. Seeded ``image_url`` custom property fallback for legacy stub rows.
        """
        empty: dict[str, Any] = {"thumbnail_url": None, "image_srcset": "", "image_sizes": ""}
        if media is None:
            return empty

        has_thumb = media.has_generated_conversion("thumbnail")
        has_card = media.has_generated_conversion("card")

        seeded_url = media.get_custom_property("image_url")
        if seeded_url and not has_thumb and not has_card:
            return {"thumbnail_url": str(seeded_url), "image_srcset": "", "image_sizes": ""}

        thumbnail_url: str | None = (
            await media.get_url("thumbnail") if has_thumb else await media.get_url()
        )

        image_srcset = ""
        if has_card:
            # Prefer the per-conversion responsive srcset — richer width steps.
            image_srcset = await media.get_srcset("card")
            if not image_srcset:
                # card exists but responsive wasn't generated — build static hints.
                parts: list[str] = [f"{await media.get_url('card')} 400w"]
                if media.has_generated_conversion("full"):
                    parts.append(f"{await media.get_url('full')} 1200w")
                image_srcset = ", ".join(parts)

        return {
            "thumbnail_url": thumbnail_url,
            "image_srcset": image_srcset,
            "image_sizes": "(min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
            if image_srcset
            else "",
        }

    @staticmethod
    def _product_to_storefront(
        product: ProductCatalog,
        locale: str,
        *,
        image_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        name_data: dict[str, Any] = product.name or {}
        slug_data: dict[str, Any] = product.slug or {}
        desc_data: dict[str, Any] = product.description or {}
        category_name_data: dict[str, Any] = product.category_name or {}
        category_slug_data: dict[str, Any] = product.category_slug or {}
        parent_cat_name_data: dict[str, Any] = product.parent_category_name or {}
        parent_cat_slug_data: dict[str, Any] = product.parent_category_slug or {}
        images = image_payload or {
            "thumbnail_url": None,
            "image_srcset": "",
            "image_sizes": "",
        }
        return {
            "id": str(product.id),
            "name": TranslatableMixin.translate_dict(name_data, locale),
            "slug": TranslatableMixin.translate_dict(slug_data, locale),
            # short_description matches the ProductCard / FlashSale frontend interface
            "short_description": TranslatableMixin.translate_dict(desc_data, locale),
            "price": float(product.price or 0),
            # stock matches ProductCard.stock — the ORM column is stock_qty
            "stock": int(product.stock_qty or 0),
            # optional fields: not yet in DB schema, return safe defaults
            "original_price": None,
            "thumbnail_url": images["thumbnail_url"],
            "image_srcset": images["image_srcset"],
            "image_sizes": images["image_sizes"],
            "rating": None,
            "rating_count": None,
            "is_new": False,
            "is_bestseller": False,
            "category_id": str(product.category_id or ""),
            "category_name": TranslatableMixin.translate_dict(category_name_data, locale),
            "category_slug": TranslatableMixin.translate_dict(category_slug_data, locale),
            "category_parent_id": str(product.category_parent_id)
            if product.category_parent_id
            else None,
            "parent_category_name": TranslatableMixin.translate_dict(parent_cat_name_data, locale)
            or None,
            "parent_category_slug": TranslatableMixin.translate_dict(parent_cat_slug_data, locale)
            or None,
            "vendor_id": str(product.vendor_id or ""),
            "vendor_name": product.vendor_name or "",
            "vendor_slug": product.vendor_slug or "",
        }

    @staticmethod
    def _product_to_admin(product: Product | ProductCatalog) -> dict[str, Any]:
        deleted_at = getattr(product, "deleted_at", None)
        real_status: str | None = getattr(product, "real_status", None)
        return {
            "id": str(product.id),
            "name": product.name or {},
            "slug": product.slug or {},
            "description": product.description or {},
            "price": float(product.price or 0),
            "stock_qty": int(product.stock_qty or 0),
            "status": product.status or "draft",
            "real_status": real_status,
            "published_at": product.published_at.isoformat() if product.published_at else None,
            "category_id": str(product.category_id or ""),
            "vendor_id": str(product.vendor_id or ""),
            "created_at": product.created_at.isoformat() if product.created_at else None,
            "updated_at": product.updated_at.isoformat() if product.updated_at else None,
            "deleted_at": deleted_at.isoformat() if deleted_at else None,
        }


__all__ = ["InsufficientStockError", "ProductNotFoundError", "ProductService"]
