"""Category service — business logic for category lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

from arvel.database import PublishableMixin

from app.http.controllers._schemas import CreateCategoryPayload, UpdateCategoryPayload
from app.models.category import Category
from app.models.product_catalog import ProductCatalog


class CategoryService:
    async def list_with_visible_products(self) -> list[dict[str, Any]]:
        """Return only categories that have at least one storefront-visible product."""
        # real_status='visible' implies the category is published and not soft-deleted;
        # SoftDeletes global scope on Category.query() handles the deleted_at filter.
        items = cast(
            "list[Category]",
            await Category.where_has(
                "catalog_products",
                lambda q: q.where(ProductCatalog.real_status == "visible"),
            )
            .order_by_raw("name->>'en'")
            .all(),
        )
        return [self.to_dict(c) for c in items]

    async def list(
        self,
        trashed: Literal["without", "with", "only"],
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        if trashed == "only":
            query = Category.only_trashed()
        elif trashed == "with":
            query = Category.with_trashed()
        else:
            query = Category.query()
        total: int = await query.count()
        items = cast(
            "list[Category]",
            await query.order_by("created_at").limit(limit).offset(offset).all(),
        )
        return {"data": [self.to_dict(c) for c in items], "total": total}

    async def find(self, category_id: str, *, include_trashed: bool = False) -> Category | None:
        try:
            cid = uuid.UUID(category_id)
        except ValueError:
            return None
        if include_trashed:
            return await Category.with_trashed().where(Category.id == cid).first()
        return await Category.where(Category.id == cid).first()

    async def create(self, payload: CreateCategoryPayload) -> Category:
        category = await Category.create(
            name=payload.name,
            slug=payload.slug,
            parent_id=uuid.UUID(payload.parent_id) if payload.parent_id else None,
            status=payload.status,
            published_at=PublishableMixin.resolve_published_at(
                payload.status, payload.published_at
            ),
        )
        if category is None:
            raise RuntimeError("Category creation failed.")
        return category

    async def update(self, category: Category, payload: UpdateCategoryPayload) -> Category:
        for key, value in payload.model_dump(exclude_unset=True).items():
            if key == "parent_id" and value is not None:
                category.parent_id = uuid.UUID(value)
            else:
                setattr(category, key, value)
        if payload.status is not None:
            category.published_at = PublishableMixin.resolve_published_at(
                payload.status, payload.published_at
            )
        await category.save()
        return category

    async def publish(self, category: Category) -> Category:
        category.status = "published"
        category.published_at = datetime.now(UTC)
        await category.save()
        return category

    async def unpublish(self, category: Category) -> Category:
        category.status = "draft"
        category.published_at = None
        await category.save()
        return category

    async def delete(self, category: Category) -> None:
        await category.delete()

    async def force_delete(self, category: Category) -> None:
        await category.force_delete()

    async def restore(self, category: Category) -> Category:
        await category.restore()
        return category

    def to_dict(self, category: Category) -> dict[str, Any]:
        return {
            "id": str(category.id),
            "name": category.name,
            "slug": category.slug or {},
            "status": category.status,
            "published_at": category.published_at.isoformat() if category.published_at else None,
            "parent_id": str(category.parent_id) if category.parent_id else None,
            "deleted_at": category.deleted_at.isoformat() if category.deleted_at else None,
        }
