"""Admin categories controller."""

from __future__ import annotations

from typing import Any

from app.http.controllers._deps import categories, require_permission, require_role_level
from app.http.controllers._schemas import CreateCategoryPayload, UpdateCategoryPayload
from arvel.database import parse_trashed_mode
from arvel.http import Request
from arvel.http.controller import Controller
from arvel.http.exceptions import NotFoundException
from starlette.responses import Response


class AdminCategoriesController(Controller):
    async def index(
        self,
        request: Request,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        await require_permission(request, "categories.view")
        return await categories.list(parse_trashed_mode(request), limit=limit, offset=offset)

    async def show(self, category_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "categories.view")
        category = await categories.find(category_id, include_trashed=True)
        if category is None:
            raise NotFoundException("Category not found.")
        return {"data": categories.to_dict(category)}

    async def store(self, payload: CreateCategoryPayload, request: Request) -> dict[str, Any]:
        await require_permission(request, "categories.create")
        category = await categories.create(payload)
        return {"data": categories.to_dict(category)}

    async def update(
        self, category_id: str, payload: UpdateCategoryPayload, request: Request
    ) -> dict[str, Any]:
        await require_permission(request, "categories.update")
        category = await categories.find(category_id, include_trashed=True)
        if category is None:
            raise NotFoundException("Category not found.")
        category = await categories.update(category, payload)
        return {"data": categories.to_dict(category)}

    async def publish(self, category_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "categories.update")
        category = await categories.find(category_id, include_trashed=True)
        if category is None:
            raise NotFoundException("Category not found.")
        category = await categories.publish(category)
        return {"data": categories.to_dict(category)}

    async def unpublish(self, category_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "categories.update")
        category = await categories.find(category_id, include_trashed=True)
        if category is None:
            raise NotFoundException("Category not found.")
        category = await categories.unpublish(category)
        return {"data": categories.to_dict(category)}

    async def destroy(self, category_id: str, request: Request) -> Response:
        await require_permission(request, "categories.delete")
        category = await categories.find(category_id)
        if category is not None:
            await categories.delete(category)
        return Response(status_code=204)

    async def force_destroy(self, category_id: str, request: Request) -> Response:
        await require_role_level(request, "categories.delete", 100)
        category = await categories.find(category_id, include_trashed=True)
        if category is not None:
            await categories.force_delete(category)
        return Response(status_code=204)

    async def restore(self, category_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "categories.update")
        category = await categories.find(category_id, include_trashed=True)
        if category is None:
            raise NotFoundException("Category not found.")
        category = await categories.restore(category)
        return {"data": categories.to_dict(category)}
