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
from app.http.requests.product_request import validate_product_fks
from app.models.product import Product
from app.services.media_service import (
    attach_product_image,
    delete_product_image,
    list_product_images,
)
from arvel.config import config
from arvel.http import File, Request, Response, UploadFile
from arvel.http.controller import Controller
from arvel.http.exceptions import BadRequestException, NotFoundException
from arvel_image.media.exceptions import (
    ConversionFailedError,
    FileTooLargeError,
    InvalidMimeTypeError,
)

_IMAGE_UPLOAD_FIELD: UploadFile = File(..., description="Product image (JPEG, PNG, WebP, GIF).")


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
        data = payload.model_dump()
        await validate_product_fks(data)
        product = await products.create(data)
        return AdminProductWrapperOut.model_validate({"data": product})

    async def update(
        self, product_id: str, payload: UpdateProductPayload, request: Request
    ) -> AdminProductWrapperOut:
        await require_permission(request, "products.update")
        # Guard first so a missing product (or malformed id) is a 404, not a 500.
        if await products.admin_get(product_id, include_trashed=True) is None:
            raise NotFoundException("Product not found.")
        changes = payload.model_dump(exclude_unset=True)
        await validate_product_fks(changes)
        product = await products.update(product_id, changes)
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
        product = await _product_model(product_id)
        if product is None:
            raise NotFoundException("Product not found.")
        # Bound the in-memory read at the collection's configured ceiling (+1 so an
        # over-limit body still trips the collection's size check instead of being
        # silently truncated). Size, MIME, and content validation all belong to the
        # arvel-image collection — see config/image.py — not to this controller.
        max_bytes = int(config("image.collections.images.max_size_bytes", 5 * 1024 * 1024))
        contents = await file.read(max_bytes + 1)
        try:
            media = await attach_product_image(product, contents, file.filename or "upload")
        except (FileTooLargeError, InvalidMimeTypeError) as exc:
            raise BadRequestException(str(exc)) from exc
        except ConversionFailedError as exc:
            # Passed the MIME gate via filename but Pillow couldn't decode it.
            raise BadRequestException("File content is not a valid image.") from exc
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
