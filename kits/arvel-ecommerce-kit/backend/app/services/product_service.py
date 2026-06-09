"""ProductService — all product-level DB operations.

Storefront reads use ProductCatalog ViewModel filtered to real_status='visible'.
Admin CRUD uses Product ORM directly; admin list uses ProductCatalog so real_status
is available without a join.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, TypedDict

from arvel.config import config
from arvel.database import TranslatableMixin
from arvel.database.exceptions import InvalidCursorError
from arvel.http.exceptions import ValidationException
from arvel.logging.facade import Log

from app.models.category import Category
from app.models.product import Product
from app.models.product_catalog import ProductCatalog
from app.models.vendor import Vendor
from app.support.labels import label
from app.support.products_catalog import refresh_products_catalog_now


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

        # A bad cursor is a client error, not a silent reset: the storefront appends
        # pages, so falling back to page one would duplicate rows in the grid.
        try:
            page = await query.cursor_paginate(
                limit,
                cursor=cursor,
                keyset=["published_at DESC", "id ASC"],
            )
        except InvalidCursorError as exc:
            raise ValidationException("Invalid pagination cursor.") from exc

        return {
            "data": [self.product_to_storefront(p, locale) for p in page.items],
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
        return self.product_to_storefront(product, locale)

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
        return [self.product_to_storefront(p, locale) for p in products]

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
        """Manually refresh products_catalog and return the indexed count.

        Uses the unconditional helper, not the lock-guarded one: an admin who
        clicks "Refresh" expects an actual refresh and a real count, never the
        ``-1`` skip sentinel. Postgres serializes any concurrent CONCURRENTLY
        refresh on the same view, so there's no thundering-herd risk.
        """
        count = await refresh_products_catalog_now()
        return {
            "refreshed_at": datetime.now(UTC).isoformat(),
            "product_count": int(count),
        }

    # ─── admin create / update ────────────────────────────────────────────────

    @staticmethod
    async def _resolve_category_id(raw: Any) -> uuid.UUID | None:
        """Parse and verify a category FK, or None when blank.

        Both checks turn what would otherwise be a 500 into a 422: a malformed
        UUID raises ValueError on the cast, and a valid-but-missing id trips the
        DB FK constraint. with_trashed mirrors the FK — a soft-deleted row still
        exists in the table, so the constraint is satisfied.
        """
        if not raw:
            return None
        try:
            cid = uuid.UUID(str(raw))
        except ValueError as exc:
            raise ValidationException("Invalid category id.") from exc
        if await Category.with_trashed().where(Category.id == cid).count() == 0:
            raise ValidationException("Category not found.")
        return cid

    @staticmethod
    async def _resolve_vendor_id(raw: Any) -> uuid.UUID | None:
        """Parse and verify a vendor FK, or None when blank. See _resolve_category_id."""
        if not raw:
            return None
        try:
            vid = uuid.UUID(str(raw))
        except ValueError as exc:
            raise ValidationException("Invalid vendor id.") from exc
        if await Vendor.with_trashed().where(Vendor.id == vid).count() == 0:
            raise ValidationException("Vendor not found.")
        return vid

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        Log.debug("product.creating", name=label(data.get("name")))
        category_id = await self._resolve_category_id(data.get("category_id"))
        vendor_id = await self._resolve_vendor_id(data.get("vendor_id"))
        product: Product = await Product.create(
            name=data.get("name", {}),
            slug=data.get("slug", {}),
            description=data.get("description", {}),
            price=Decimal(str(data["price"])),
            stock_qty=data.get("stock_qty", 0),
            status="draft",
            category_id=category_id,
            vendor_id=vendor_id,
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
            elif key == "category_id":
                product.category_id = await self._resolve_category_id(val)
            elif key == "vendor_id":
                product.vendor_id = await self._resolve_vendor_id(val)
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

    _IMAGE_SIZES = "(min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"

    @classmethod
    def product_to_storefront(cls, product: ProductCatalog, locale: str) -> dict[str, Any]:
        # Media.to_dict() yields the full per-image payload (url, conversions,
        # srcsets, placeholder_svg). The card-view flat fields below pluck the
        # named conversion / srcset that the storefront card expects.
        images = [m.to_dict() for m in product.media]
        first = images[0] if images else None
        thumbnail_url = (first["conversions"].get("thumbnail") or first["url"]) if first else None
        card_srcset = first["srcsets"].get("card", "") if first else ""
        # Without responsive variants, hint at the card-conversion width so the
        # browser still picks a sane source for non-1x displays.
        if first and not card_srcset:
            card_url = first["conversions"].get("card")
            if card_url and card_url != first["url"]:
                card_srcset = f"{card_url} 400w"

        created = product.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        new_window = timedelta(days=int(config("catalog.new_product_days", 30)))
        is_new = created is not None and (datetime.now(UTC) - created) <= new_window

        tr = TranslatableMixin.translate_dict
        name: dict[str, Any] = product.name or {}
        slug: dict[str, Any] = product.slug or {}
        desc: dict[str, Any] = product.description or {}
        cat_name: dict[str, Any] = product.category_name or {}
        cat_slug: dict[str, Any] = product.category_slug or {}
        parent_cat_name: dict[str, Any] = product.parent_category_name or {}
        parent_cat_slug: dict[str, Any] = product.parent_category_slug or {}

        return {
            "id": str(product.id),
            "name": tr(name, locale),
            "slug": tr(slug, locale),
            "short_description": tr(desc, locale),
            "price": float(product.price or 0),
            "stock": int(product.stock_qty or 0),
            "original_price": None,
            "thumbnail_url": thumbnail_url,
            "image_srcset": card_srcset,
            "image_sizes": cls._IMAGE_SIZES if card_srcset else "",
            "images": images,
            "rating": None,
            "rating_count": None,
            "is_new": is_new,
            # No order-count signal in the catalog view; stays false until there's a
            # real bestseller metric rather than a fabricated badge.
            "is_bestseller": False,
            "category_id": str(product.category_id or ""),
            "category_name": tr(cat_name, locale),
            "category_slug": tr(cat_slug, locale),
            "category_parent_id": str(product.category_parent_id)
            if product.category_parent_id
            else None,
            "parent_category_name": tr(parent_cat_name, locale) or None,
            "parent_category_slug": tr(parent_cat_slug, locale) or None,
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
