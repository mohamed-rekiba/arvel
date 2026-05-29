"""Admin vendors controller."""

from __future__ import annotations

from typing import Any

from app.http.controllers._deps import require_permission, require_role_level, vendors
from app.http.controllers._schemas import CreateVendorPayload, UpdateVendorPayload
from arvel.database import parse_trashed_mode
from arvel.http.controller import Controller
from arvel.http.exceptions import NotFoundException
from starlette.requests import Request
from starlette.responses import Response


class AdminVendorsController(Controller):
    async def index(
        self,
        request: Request,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        await require_permission(request, "vendors.view")
        return await vendors.list(parse_trashed_mode(request), limit=limit, offset=offset)

    async def show(self, vendor_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "vendors.view")
        vendor = await vendors.find(vendor_id, include_trashed=True)
        if vendor is None:
            raise NotFoundException("Vendor not found.")
        return {"data": vendors.to_dict(vendor)}

    async def store(self, payload: CreateVendorPayload, request: Request) -> dict[str, Any]:
        await require_permission(request, "vendors.create")
        vendor = await vendors.create(payload)
        return {"data": vendors.to_dict(vendor)}

    async def update(
        self, vendor_id: str, payload: UpdateVendorPayload, request: Request
    ) -> dict[str, Any]:
        await require_permission(request, "vendors.update")
        vendor = await vendors.find(vendor_id, include_trashed=True)
        if vendor is None:
            raise NotFoundException("Vendor not found.")
        vendor = await vendors.update(vendor, payload)
        return {"data": vendors.to_dict(vendor)}

    async def publish(self, vendor_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "vendors.update")
        vendor = await vendors.find(vendor_id, include_trashed=True)
        if vendor is None:
            raise NotFoundException("Vendor not found.")
        vendor = await vendors.publish(vendor)
        return {"data": vendors.to_dict(vendor)}

    async def unpublish(self, vendor_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "vendors.update")
        vendor = await vendors.find(vendor_id, include_trashed=True)
        if vendor is None:
            raise NotFoundException("Vendor not found.")
        vendor = await vendors.unpublish(vendor)
        return {"data": vendors.to_dict(vendor)}

    async def destroy(self, vendor_id: str, request: Request) -> Response:
        await require_permission(request, "vendors.delete")
        vendor = await vendors.find(vendor_id)
        if vendor is not None:
            await vendors.delete(vendor)
        return Response(status_code=204)

    async def force_destroy(self, vendor_id: str, request: Request) -> Response:
        await require_role_level(request, "vendors.delete", 100)
        vendor = await vendors.find(vendor_id, include_trashed=True)
        if vendor is not None:
            await vendors.force_delete(vendor)
        return Response(status_code=204)

    async def restore(self, vendor_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "vendors.update")
        vendor = await vendors.find(vendor_id, include_trashed=True)
        if vendor is None:
            raise NotFoundException("Vendor not found.")
        vendor = await vendors.restore(vendor)
        return {"data": vendors.to_dict(vendor)}
