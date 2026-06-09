"""Category service — business logic for category lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

from arvel.database import PublishableMixin
from arvel.http.exceptions import ConflictException, ValidationException
from arvel.logging.facade import Log

from app.http.controllers._schemas import CreateCategoryPayload, UpdateCategoryPayload
from app.models.category import Category
from app.models.product import Product
from app.support.labels import label


class CategoryService:
    async def list_with_visible_products(self) -> list[dict[str, Any]]:
        """Return only categories that have at least one storefront-visible product."""
        # real_status='visible' implies the category is published and not soft-deleted;
        # SoftDeletes global scope on Category.query() handles the deleted_at filter.
        items = cast(
            "list[Category]",
            await Category.where_has(
                "catalog_products",
                lambda q: q.visible(),
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

    @staticmethod
    def _coerce_parent_id(raw: str) -> uuid.UUID:
        # Request-layer parsing: a malformed parent_id is a 422, not a 500. Mirrors
        # validate_product_fks' coercion so both FK paths fail the same clean way.
        try:
            return uuid.UUID(raw)
        except ValueError as exc:
            raise ValidationException(
                "Validation failed.",
                details=[{"field": "parent_id", "issue": "must be a valid UUID"}],
            ) from exc

    async def _assert_acyclic_parent(self, category: Category, parent_id: uuid.UUID) -> None:
        """Reject self-parenting and cycles before writing parent_id."""
        if parent_id == category.id:
            raise ValidationException("A category cannot be its own parent.")
        # Walk the proposed parent's ancestor chain; hitting this category means
        # the new edge closes a loop. seen[] guards against a pre-existing cycle.
        cursor: Category | None = (
            await Category.with_trashed().where(Category.id == parent_id).first()
        )
        if cursor is None:
            raise ValidationException("Parent category not found.")
        seen: set[uuid.UUID] = set()
        while cursor is not None and cursor.parent_id is not None:
            if cursor.parent_id == category.id:
                raise ValidationException("Category parent would create a cycle.")
            if cursor.parent_id in seen:
                break
            seen.add(cursor.parent_id)
            cursor = await Category.with_trashed().where(Category.id == cursor.parent_id).first()

    async def create(self, payload: CreateCategoryPayload) -> Category:
        Log.debug("category.creating", name=label(payload.name))
        parent_uuid = self._coerce_parent_id(payload.parent_id) if payload.parent_id else None
        if parent_uuid is not None:
            parent = await Category.with_trashed().where(Category.id == parent_uuid).first()
            if parent is None:
                raise ValidationException("Parent category not found.")
        category = await Category.create(
            name=payload.name,
            slug=payload.slug,
            parent_id=parent_uuid,
            status=payload.status,
            published_at=PublishableMixin.resolve_published_at(
                payload.status, payload.published_at
            ),
        )
        if category is None:
            raise RuntimeError("Category creation failed.")
        Log.debug("category.created", category_id=str(category.id))
        return category

    async def update(self, category: Category, payload: UpdateCategoryPayload) -> Category:
        Log.debug("category.updating", category_id=str(category.id))
        for key, value in payload.model_dump(exclude_unset=True).items():
            if key == "parent_id" and value is not None:
                new_parent = self._coerce_parent_id(value)
                await self._assert_acyclic_parent(category, new_parent)
                category.parent_id = new_parent
            else:
                setattr(category, key, value)
        if payload.status is not None:
            category.published_at = PublishableMixin.resolve_published_at(
                payload.status, payload.published_at
            )
        await category.save()
        Log.debug("category.updated", category_id=str(category.id))
        return category

    async def publish(self, category: Category) -> Category:
        Log.debug("category.publishing", category_id=str(category.id))
        category.status = "published"
        category.published_at = datetime.now(UTC)
        await category.save()
        Log.debug("category.published", category_id=str(category.id))
        return category

    async def unpublish(self, category: Category) -> Category:
        Log.debug("category.unpublishing", category_id=str(category.id))
        category.status = "draft"
        category.published_at = None
        await category.save()
        Log.debug("category.unpublished", category_id=str(category.id))
        return category

    async def delete(self, category: Category) -> None:
        Log.debug("category.deleting", category_id=str(category.id))
        await category.delete()
        Log.debug("category.deleted", category_id=str(category.id))

    async def force_delete(self, category: Category) -> None:
        # products.category_id and the self-referential parent_id are FK RESTRICT.
        # Soft-deleted rows still hold the FK, so check with_trashed — otherwise the
        # hard delete trips a DB-level violation and surfaces as a 500 instead of 409.
        if await Product.with_trashed().where(Product.category_id == category.id).count():
            raise ConflictException("Cannot permanently delete a category that has products.")
        if await Category.with_trashed().where(Category.parent_id == category.id).count():
            raise ConflictException("Cannot permanently delete a category that has subcategories.")
        Log.debug("category.force_deleting", category_id=str(category.id))
        await category.force_delete()
        Log.debug("category.force_deleted", category_id=str(category.id))

    async def restore(self, category: Category) -> Category:
        Log.debug("category.restoring", category_id=str(category.id))
        await category.restore()
        Log.debug("category.restored", category_id=str(category.id))
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
