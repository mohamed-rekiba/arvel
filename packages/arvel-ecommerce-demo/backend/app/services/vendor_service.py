"""Vendor service — business logic for vendor lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

from arvel.database import PublishableMixin

from app.http.controllers._schemas import CreateVendorPayload, UpdateVendorPayload
from app.models.vendor import Vendor


class VendorService:
    async def list(
        self,
        trashed: Literal["without", "with", "only"],
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        if trashed == "only":
            query = Vendor.only_trashed()
        elif trashed == "with":
            query = Vendor.with_trashed()
        else:
            query = Vendor.query()
        total: int = await query.count()
        items = cast(
            "list[Vendor]",
            await query.order_by("created_at").limit(limit).offset(offset).all(),
        )
        return {"data": [self.to_dict(v) for v in items], "total": total}

    async def find(self, vendor_id: str, *, include_trashed: bool = False) -> Vendor | None:
        try:
            vid = uuid.UUID(vendor_id)
        except ValueError:
            return None
        if include_trashed:
            return await Vendor.with_trashed().where(Vendor.id == vid).first()
        return await Vendor.where(Vendor.id == vid).first()

    async def create(self, payload: CreateVendorPayload) -> Vendor:
        vendor = await Vendor.create(
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            status=payload.status,
            published_at=PublishableMixin.resolve_published_at(
                payload.status, payload.published_at
            ),
        )
        if vendor is None:
            raise RuntimeError("Vendor creation failed.")
        return vendor

    async def update(self, vendor: Vendor, payload: UpdateVendorPayload) -> Vendor:
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(vendor, key, value)
        if payload.status is not None:
            vendor.published_at = PublishableMixin.resolve_published_at(
                payload.status, payload.published_at
            )
        await vendor.save()
        return vendor

    async def publish(self, vendor: Vendor) -> Vendor:
        vendor.status = "published"
        vendor.published_at = datetime.now(UTC)
        await vendor.save()
        return vendor

    async def unpublish(self, vendor: Vendor) -> Vendor:
        vendor.status = "draft"
        vendor.published_at = None
        await vendor.save()
        return vendor

    async def delete(self, vendor: Vendor) -> None:
        await vendor.delete()

    async def force_delete(self, vendor: Vendor) -> None:
        await vendor.force_delete()

    async def restore(self, vendor: Vendor) -> Vendor:
        await vendor.restore()
        return vendor

    def to_dict(self, vendor: Vendor) -> dict[str, Any]:
        return {
            "id": str(vendor.id),
            "name": vendor.name,
            "slug": vendor.slug,
            "description": vendor.description,
            "status": vendor.status,
            "published_at": vendor.published_at.isoformat() if vendor.published_at else None,
            "deleted_at": vendor.deleted_at.isoformat() if vendor.deleted_at else None,
        }
