"""Admin categories controller."""

from __future__ import annotations

from typing import Literal

from app.http.controllers._deps import (
    categories,
    clamp_limit,
    clamp_offset,
    require_permission,
    require_role_level,
)
from app.http.controllers._responses import AdminCategoryListOut, AdminCategoryWrapperOut
from app.http.controllers._schemas import CreateCategoryPayload, UpdateCategoryPayload
from arvel.http import Request
from arvel.http.controller import Controller
from arvel.http.exceptions import NotFoundException
from starlette.responses import Response


class AdminCategoriesController(Controller):
    async def index(
        self,
        request: Request,
        trashed: Literal["without", "with", "only"] = "without",
        limit: int = 50,
        offset: int = 0,
    ) -> AdminCategoryListOut:
        await require_permission(request, "categories.view")
        return AdminCategoryListOut.model_validate(
            await categories.list(trashed, limit=clamp_limit(limit), offset=clamp_offset(offset))
        )

    async def show(self, category_id: str, request: Request) -> AdminCategoryWrapperOut:
        await require_permission(request, "categories.view")
        category = await categories.find(category_id, include_trashed=True)
        if category is None:
            raise NotFoundException("Category not found.")
        return AdminCategoryWrapperOut.model_validate({"data": categories.to_dict(category)})

    async def store(
        self, payload: CreateCategoryPayload, request: Request
    ) -> AdminCategoryWrapperOut:
        await require_permission(request, "categories.create")
        category = await categories.create(payload)
        return AdminCategoryWrapperOut.model_validate({"data": categories.to_dict(category)})

    async def update(
        self, category_id: str, payload: UpdateCategoryPayload, request: Request
    ) -> AdminCategoryWrapperOut:
        await require_permission(request, "categories.update")
        category = await categories.find(category_id, include_trashed=True)
        if category is None:
            raise NotFoundException("Category not found.")
        category = await categories.update(category, payload)
        return AdminCategoryWrapperOut.model_validate({"data": categories.to_dict(category)})

    async def publish(self, category_id: str, request: Request) -> AdminCategoryWrapperOut:
        await require_permission(request, "categories.update")
        category = await categories.find(category_id, include_trashed=True)
        if category is None:
            raise NotFoundException("Category not found.")
        category = await categories.publish(category)
        return AdminCategoryWrapperOut.model_validate({"data": categories.to_dict(category)})

    async def unpublish(self, category_id: str, request: Request) -> AdminCategoryWrapperOut:
        await require_permission(request, "categories.update")
        category = await categories.find(category_id, include_trashed=True)
        if category is None:
            raise NotFoundException("Category not found.")
        category = await categories.unpublish(category)
        return AdminCategoryWrapperOut.model_validate({"data": categories.to_dict(category)})

    async def destroy(self, category_id: str, request: Request) -> Response:
        await require_permission(request, "categories.delete")
        category = await categories.find(category_id)
        if category is None:
            raise NotFoundException("Category not found.")
        await categories.delete(category)
        return Response(status_code=204)

    async def force_destroy(self, category_id: str, request: Request) -> Response:
        await require_role_level(request, "categories.delete", 100)
        category = await categories.find(category_id, include_trashed=True)
        if category is None:
            raise NotFoundException("Category not found.")
        await categories.force_delete(category)
        return Response(status_code=204)

    async def restore(self, category_id: str, request: Request) -> AdminCategoryWrapperOut:
        await require_permission(request, "categories.update")
        category = await categories.find(category_id, include_trashed=True)
        if category is None:
            raise NotFoundException("Category not found.")
        category = await categories.restore(category)
        return AdminCategoryWrapperOut.model_validate({"data": categories.to_dict(category)})
