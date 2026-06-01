"""Vendor service — business logic for vendor lifecycle."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

from arvel.database import PublishableMixin
from arvel.logging.facade import Log

from app.http.controllers._schemas import CreateVendorPayload, UpdateVendorPayload
from app.models.vendor import Vendor
from app.support.labels import label


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
        Log.debug("vendor.creating", name=label(payload.name))
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
        Log.debug("vendor.created", vendor_id=str(vendor.id))
        return vendor

    async def update(self, vendor: Vendor, payload: UpdateVendorPayload) -> Vendor:
        Log.debug("vendor.updating", vendor_id=str(vendor.id))
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(vendor, key, value)
        if payload.status is not None:
            vendor.published_at = PublishableMixin.resolve_published_at(
                payload.status, payload.published_at
            )
        await vendor.save()
        Log.debug("vendor.updated", vendor_id=str(vendor.id))
        return vendor

    async def publish(self, vendor: Vendor) -> Vendor:
        Log.debug("vendor.publishing", vendor_id=str(vendor.id))
        vendor.status = "published"
        vendor.published_at = datetime.now(UTC)
        await vendor.save()
        Log.debug("vendor.published", vendor_id=str(vendor.id))
        return vendor

    async def unpublish(self, vendor: Vendor) -> Vendor:
        Log.debug("vendor.unpublishing", vendor_id=str(vendor.id))
        vendor.status = "draft"
        vendor.published_at = None
        await vendor.save()
        Log.debug("vendor.unpublished", vendor_id=str(vendor.id))
        return vendor

    async def delete(self, vendor: Vendor) -> None:
        Log.debug("vendor.deleting", vendor_id=str(vendor.id))
        await vendor.delete()
        Log.debug("vendor.deleted", vendor_id=str(vendor.id))

    async def force_delete(self, vendor: Vendor) -> None:
        Log.debug("vendor.force_deleting", vendor_id=str(vendor.id))
        await vendor.force_delete()
        Log.debug("vendor.force_deleted", vendor_id=str(vendor.id))

    async def restore(self, vendor: Vendor) -> Vendor:
        Log.debug("vendor.restoring", vendor_id=str(vendor.id))
        await vendor.restore()
        Log.debug("vendor.restored", vendor_id=str(vendor.id))
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
