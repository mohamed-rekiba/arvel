"""Admin products controller: CRUD, soft-delete, restore, publish, media."""

from __future__ import annotations

import uuid
from typing import Literal

from app.http.controllers._deps import (
    clamp_limit,
    clamp_offset,
    products,
    require_permission,
    require_role_level,
)
from app.http.controllers._responses import (
    AdminProductListOut,
    AdminProductWrapperOut,
    CatalogRefreshOut,
    MediaListOut,
    MediaWrapperOut,
)
from app.http.controllers._schemas import CreateProductPayload, UpdateProductPayload
from app.models.product import Product
from app.services.media_service import (
    attach_product_image,
    delete_product_image,
    list_product_images,
)
from arvel.http import File, Request, Response, UploadFile
from arvel.http.controller import Controller
from arvel.http.exceptions import BadRequestException, NotFoundException

_ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
_IMAGE_UPLOAD_FIELD: UploadFile = File(..., description="Product image (JPEG, PNG, WebP, GIF).")
# Cap uploads so a single request can't read an unbounded blob into worker memory.
_MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _sniff_image_type(data: bytes) -> str | None:
    """Return the image MIME from magic bytes, or None if it's not an image we accept."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def _product_model(product_id: str) -> Product | None:
    try:
        pid = uuid.UUID(product_id)
    except ValueError:
        return None
    return await Product.where(Product.id == pid).with_("media").first()


class AdminProductsController(Controller):
    async def index(
        self,
        request: Request,
        trashed: Literal["without", "with", "only"] = "without",
        limit: int = 50,
        offset: int = 0,
    ) -> AdminProductListOut:
        await require_permission(request, "products.view")
        return AdminProductListOut.model_validate(
            await products.admin_list(
                filters={
                    "trashed": trashed,
                    "status": request.query_params.get("status"),
                    "real_status": request.query_params.get("real_status"),
                    "slug": request.query_params.get("slug"),
                    "limit": clamp_limit(limit),
                    "offset": clamp_offset(offset),
                }
            )
        )

    async def show(self, product_id: str, request: Request) -> AdminProductWrapperOut:
        await require_permission(request, "products.view")
        product = await products.admin_get(product_id, include_trashed=True)
        if product is None:
            raise NotFoundException("Product not found.")
        return AdminProductWrapperOut.model_validate({"data": product})

    async def store(
        self, payload: CreateProductPayload, request: Request
    ) -> AdminProductWrapperOut:
        await require_permission(request, "products.create")
        product = await products.create(payload.model_dump())
        return AdminProductWrapperOut.model_validate({"data": product})

    async def update(
        self, product_id: str, payload: UpdateProductPayload, request: Request
    ) -> AdminProductWrapperOut:
        await require_permission(request, "products.update")
        # Guard first so a missing product (or malformed id) is a 404, not a 500.
        if await products.admin_get(product_id, include_trashed=True) is None:
            raise NotFoundException("Product not found.")
        product = await products.update(product_id, payload.model_dump(exclude_unset=True))
        return AdminProductWrapperOut.model_validate({"data": product})

    async def destroy(self, product_id: str, request: Request) -> Response:
        await require_permission(request, "products.delete")
        if await products.admin_get(product_id, include_trashed=True) is None:
            raise NotFoundException("Product not found.")
        await products.soft_delete(product_id)
        return Response(status_code=204)

    async def force_destroy(self, product_id: str, request: Request) -> Response:
        await require_role_level(request, "products.delete", 100)
        if await products.admin_get(product_id, include_trashed=True) is None:
            raise NotFoundException("Product not found.")
        await products.force_delete(product_id)
        return Response(status_code=204)

    async def restore(self, product_id: str, request: Request) -> AdminProductWrapperOut:
        await require_permission(request, "products.restore")
        product = await products.restore(product_id)
        if product is None:
            raise NotFoundException("Product not found.")
        return AdminProductWrapperOut.model_validate({"data": product})

    async def publish(self, product_id: str, request: Request) -> AdminProductWrapperOut:
        await require_permission(request, "products.publish")
        product = await products.publish(product_id)
        if product is None:
            raise NotFoundException("Product not found.")
        return AdminProductWrapperOut.model_validate({"data": product})

    async def unpublish(self, product_id: str, request: Request) -> AdminProductWrapperOut:
        await require_permission(request, "products.publish")
        product = await products.unpublish(product_id)
        if product is None:
            raise NotFoundException("Product not found.")
        return AdminProductWrapperOut.model_validate({"data": product})

    async def catalog_refresh(self, request: Request) -> CatalogRefreshOut:
        # catalog/refresh is the on-demand trigger; background auto-refresh
        # is handled by ProductsCatalogRefreshObserver.
        await require_permission(request, "products.view")
        return CatalogRefreshOut.model_validate(await products.refresh_catalog())

    async def media_store(
        self,
        product_id: str,
        request: Request,
        file: UploadFile = _IMAGE_UPLOAD_FIELD,
    ) -> MediaWrapperOut:
        await require_permission(request, "products.update")
        mime = file.content_type or ""
        if mime not in _ALLOWED_IMAGE_TYPES:
            raise BadRequestException(
                f"Unsupported media type '{mime}'. Upload JPEG, PNG, WebP, or GIF."
            )
        # Read at most the cap + 1 byte: bounds memory even when the client omits
        # Content-Length (file.size is None), which the header-only check missed.
        contents = await file.read(_MAX_IMAGE_BYTES + 1)
        if len(contents) > _MAX_IMAGE_BYTES:
            raise BadRequestException(
                f"Image exceeds the {_MAX_IMAGE_BYTES // (1024 * 1024)} MB upload limit."
            )
        # Don't trust the declared content-type — sniff the magic bytes so a
        # non-image payload can't ride in under an image/* header.
        if _sniff_image_type(contents) is None:
            raise BadRequestException("File content is not a recognized image.")
        product = await _product_model(product_id)
        if product is None:
            raise NotFoundException("Product not found.")
        media = await attach_product_image(product, contents, file.filename or "upload")
        return MediaWrapperOut.model_validate({"data": media})

    async def media_index(self, product_id: str, request: Request) -> MediaListOut:
        await require_permission(request, "products.view")
        product = await _product_model(product_id)
        if product is None:
            raise NotFoundException("Product not found.")
        return MediaListOut.model_validate({"data": list_product_images(product)})

    async def media_destroy(self, product_id: str, media_id: str, request: Request) -> Response:
        await require_permission(request, "products.update")
        product = await _product_model(product_id)
        if product is None:
            raise NotFoundException("Product not found.")
        deleted = await delete_product_image(product, media_id)
        if not deleted:
            raise NotFoundException("Media not found.")
        return Response(status_code=204)
