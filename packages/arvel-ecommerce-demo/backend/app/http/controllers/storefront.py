"""Storefront controller: public product listing, categories, search."""

from __future__ import annotations

from typing import Any

from app.http.controllers._deps import categories, products
from app.http.controllers._responses import StorefrontCategoryListOut
from arvel.http.controller import Controller
from arvel.http.exceptions import BadRequestException, NotFoundException
from starlette.requests import Request

_MIN_QUERY_LENGTH = 2


class StorefrontController(Controller):
    async def index(
        self,
        request: Request,
        limit: int = 20,
        cursor: str | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        resolved_locale = locale or getattr(request.state, "locale", "en") or "en"
        return await products.list_published(locale=resolved_locale, limit=limit, cursor=cursor)

    async def show(
        self,
        slug: str,
        request: Request,
        locale: str | None = None,
    ) -> dict[str, Any]:
        resolved_locale = locale or getattr(request.state, "locale", "en") or "en"
        product = await products.get_published_by_slug(slug, resolved_locale)
        if product is None:
            raise NotFoundException(f"Product '{slug}' not found.")
        return {"data": product}

    async def category_products(
        self,
        slug: str,
        request: Request,
        limit: int = 20,
        cursor: str | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        resolved_locale = locale or getattr(request.state, "locale", "en") or "en"
        return await products.list_published_by_category_slug(
            slug, locale=resolved_locale, limit=limit, cursor=cursor
        )

    async def categories_index(self) -> StorefrontCategoryListOut:
        return StorefrontCategoryListOut(data=await categories.list_with_visible_products())

    async def search(
        self,
        q: str,
        request: Request,
        locale: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        if len(q) < _MIN_QUERY_LENGTH:
            raise BadRequestException("Search query must be at least 2 characters.")
        resolved_locale = locale or getattr(request.state, "locale", "en") or "en"
        results = await products.search_published(q=q, locale=resolved_locale, limit=limit)
        return {"data": results}
