"""Admin vendors controller."""

from __future__ import annotations

from typing import Literal

from app.http.controllers._deps import require_permission, require_role_level, vendors
from app.http.controllers._responses import AdminVendorListOut, AdminVendorWrapperOut
from app.http.controllers._schemas import CreateVendorPayload, UpdateVendorPayload
from arvel.http import Request
from arvel.http.controller import Controller
from arvel.http.exceptions import NotFoundException
from starlette.responses import Response


class AdminVendorsController(Controller):
    async def index(
        self,
        request: Request,
        trashed: Literal["without", "with", "only"] = "without",
        limit: int = 50,
        offset: int = 0,
    ) -> AdminVendorListOut:
        await require_permission(request, "vendors.view")
        return AdminVendorListOut.model_validate(
            await vendors.list(trashed, limit=limit, offset=offset)
        )

    async def show(self, vendor_id: str, request: Request) -> AdminVendorWrapperOut:
        await require_permission(request, "vendors.view")
        vendor = await vendors.find(vendor_id, include_trashed=True)
        if vendor is None:
            raise NotFoundException("Vendor not found.")
        return AdminVendorWrapperOut.model_validate({"data": vendors.to_dict(vendor)})

    async def store(self, payload: CreateVendorPayload, request: Request) -> AdminVendorWrapperOut:
        await require_permission(request, "vendors.create")
        vendor = await vendors.create(payload)
        return AdminVendorWrapperOut.model_validate({"data": vendors.to_dict(vendor)})

    async def update(
        self, vendor_id: str, payload: UpdateVendorPayload, request: Request
    ) -> AdminVendorWrapperOut:
        await require_permission(request, "vendors.update")
        vendor = await vendors.find(vendor_id, include_trashed=True)
        if vendor is None:
            raise NotFoundException("Vendor not found.")
        vendor = await vendors.update(vendor, payload)
        return AdminVendorWrapperOut.model_validate({"data": vendors.to_dict(vendor)})

    async def publish(self, vendor_id: str, request: Request) -> AdminVendorWrapperOut:
        await require_permission(request, "vendors.update")
        vendor = await vendors.find(vendor_id, include_trashed=True)
        if vendor is None:
            raise NotFoundException("Vendor not found.")
        vendor = await vendors.publish(vendor)
        return AdminVendorWrapperOut.model_validate({"data": vendors.to_dict(vendor)})

    async def unpublish(self, vendor_id: str, request: Request) -> AdminVendorWrapperOut:
        await require_permission(request, "vendors.update")
        vendor = await vendors.find(vendor_id, include_trashed=True)
        if vendor is None:
            raise NotFoundException("Vendor not found.")
        vendor = await vendors.unpublish(vendor)
        return AdminVendorWrapperOut.model_validate({"data": vendors.to_dict(vendor)})

    async def destroy(self, vendor_id: str, request: Request) -> Response:
        await require_permission(request, "vendors.delete")
        vendor = await vendors.find(vendor_id)
        if vendor is None:
            raise NotFoundException("Vendor not found.")
        await vendors.delete(vendor)
        return Response(status_code=204)

    async def force_destroy(self, vendor_id: str, request: Request) -> Response:
        await require_role_level(request, "vendors.delete", 100)
        vendor = await vendors.find(vendor_id, include_trashed=True)
        if vendor is None:
            raise NotFoundException("Vendor not found.")
        await vendors.force_delete(vendor)
        return Response(status_code=204)

    async def restore(self, vendor_id: str, request: Request) -> AdminVendorWrapperOut:
        await require_permission(request, "vendors.update")
        vendor = await vendors.find(vendor_id, include_trashed=True)
        if vendor is None:
            raise NotFoundException("Vendor not found.")
        vendor = await vendors.restore(vendor)
        return AdminVendorWrapperOut.model_validate({"data": vendors.to_dict(vendor)})
