"""Admin products controller: CRUD, soft-delete, restore, publish, media."""

from __future__ import annotations

import uuid
from typing import Any

from app.http.controllers._deps import products, require_permission, require_role_level
from app.http.controllers._schemas import CreateProductPayload, UpdateProductPayload
from app.models.product import Product
from app.services.media_service import (
    attach_product_image,
    delete_product_image,
    list_product_images,
)
from arvel.http.controller import Controller
from arvel.http.exceptions import BadRequestException, NotFoundException, ValidationException
from fastapi import File, UploadFile
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import Response

_ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
_IMAGE_UPLOAD_FIELD: UploadFile = File(..., description="Product image (JPEG, PNG, WebP).")


async def _product_model(product_id: str) -> Product | None:
    try:
        pid = uuid.UUID(product_id)
    except ValueError:
        return None
    return await Product.where(Product.id == pid).first()


def _query_int(request: Request, name: str, default: int) -> int:
    value = request.query_params.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise BadRequestException(f"Invalid integer query parameter: {name}") from exc


class AdminProductsController(Controller):
    async def index(self, request: Request) -> dict[str, Any]:
        await require_permission(request, "products.view")
        return await products.admin_list(
            filters={
                "trashed": request.query_params.get("trashed", "without"),
                "status": request.query_params.get("status"),
                "real_status": request.query_params.get("real_status"),
                "slug": request.query_params.get("slug"),
                "limit": _query_int(request, "limit", 50),
                "offset": _query_int(request, "offset", 0),
            }
        )

    async def show(self, product_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "products.view")
        product = await products.admin_get(product_id, include_trashed=True)
        if product is None:
            raise NotFoundException("Product not found.")
        return {"data": product}

    async def store(self, request: Request) -> dict[str, Any]:
        await require_permission(request, "products.create")
        body = await request.json()
        try:
            payload = CreateProductPayload.model_validate(body)
        except ValidationError as exc:
            details = [
                {"field": ".".join(str(loc) for loc in err["loc"]), "issue": err["msg"]}
                for err in exc.errors()
            ]
            raise ValidationException("Validation failed.", details=details) from exc
        product = await products.create(payload.model_dump())
        return {"data": product}

    async def update(
        self, product_id: str, payload: UpdateProductPayload, request: Request
    ) -> dict[str, Any]:
        await require_permission(request, "products.update")
        product = await products.update(product_id, payload.model_dump(exclude_unset=True))
        return {"data": product}

    async def destroy(self, product_id: str, request: Request) -> Response:
        await require_permission(request, "products.delete")
        await products.soft_delete(product_id)
        return Response(status_code=204)

    async def force_destroy(self, product_id: str, request: Request) -> Response:
        await require_role_level(request, "products.delete", 100)
        await products.force_delete(product_id)
        return Response(status_code=204)

    async def restore(self, product_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "products.restore")
        product = await products.restore(product_id)
        if product is None:
            raise NotFoundException("Product not found.")
        return {"data": product}

    async def publish(self, product_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "products.publish")
        product = await products.publish(product_id)
        if product is None:
            raise NotFoundException("Product not found.")
        return {"data": product}

    async def unpublish(self, product_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "products.publish")
        product = await products.unpublish(product_id)
        if product is None:
            raise NotFoundException("Product not found.")
        return {"data": product}

    async def catalog_refresh(self, request: Request) -> dict[str, Any]:
        # catalog/refresh is the on-demand trigger; background auto-refresh
        # is handled by ProductsCatalogRefreshObserver.
        await require_permission(request, "products.view")
        return await products.refresh_catalog()

    async def media_store(
        self,
        product_id: str,
        request: Request,
        file: UploadFile = _IMAGE_UPLOAD_FIELD,
    ) -> dict[str, Any]:
        await require_permission(request, "products.update")
        mime = file.content_type or ""
        if mime not in _ALLOWED_IMAGE_TYPES:
            raise BadRequestException(
                f"Unsupported media type '{mime}'. Upload JPEG, PNG, or WebP."
            )
        product = await _product_model(product_id)
        if product is None:
            raise NotFoundException("Product not found.")
        media = await attach_product_image(product, file)
        return {"data": media}

    async def media_index(self, product_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "products.view")
        product = await _product_model(product_id)
        if product is None:
            raise NotFoundException("Product not found.")
        return {"data": await list_product_images(product)}

    async def media_destroy(self, product_id: str, media_id: str, request: Request) -> Response:
        await require_permission(request, "products.update")
        product = await _product_model(product_id)
        if product is None:
            raise NotFoundException("Product not found.")
        deleted = await delete_product_image(product, media_id)
        if not deleted:
            raise NotFoundException("Media not found.")
        return Response(status_code=204)
