"""Storefront controller: public product listing, categories, search."""

from __future__ import annotations

from app.http.controllers._deps import categories, clamp_limit, products
from app.http.controllers._responses import (
    ProductDetailOut,
    ProductListOut,
    SearchOut,
    StorefrontCategoryListOut,
)
from arvel.config import config
from arvel.http import Request
from arvel.http.controller import Controller
from arvel.http.exceptions import BadRequestException, NotFoundException


class StorefrontController(Controller):
    async def index(
        self,
        request: Request,
        limit: int = 20,
        cursor: str | None = None,
        locale: str | None = None,
    ) -> ProductListOut:
        resolved_locale = locale or getattr(request.state, "locale", "en") or "en"
        return ProductListOut.model_validate(
            await products.list_published(
                locale=resolved_locale, limit=clamp_limit(limit), cursor=cursor
            )
        )

    async def show(
        self,
        slug: str,
        request: Request,
        locale: str | None = None,
    ) -> ProductDetailOut:
        resolved_locale = locale or getattr(request.state, "locale", "en") or "en"
        product = await products.get_published_by_slug(slug, resolved_locale)
        if product is None:
            raise NotFoundException(f"Product '{slug}' not found.")
        return ProductDetailOut.model_validate({"data": product})

    async def products_catalog(
        self,
        slug: str,
        request: Request,
        limit: int = 20,
        cursor: str | None = None,
        locale: str | None = None,
    ) -> ProductListOut:
        resolved_locale = locale or getattr(request.state, "locale", "en") or "en"
        return ProductListOut.model_validate(
            await products.list_published_by_category_slug(
                slug, locale=resolved_locale, limit=clamp_limit(limit), cursor=cursor
            )
        )

    async def categories_index(self) -> StorefrontCategoryListOut:
        return StorefrontCategoryListOut(data=await categories.list_with_visible_products())

    async def search(
        self,
        q: str,
        request: Request,
        locale: str | None = None,
        limit: int = 20,
    ) -> SearchOut:
        min_length = int(config("catalog.search_min_length", 2))
        if len(q) < min_length:
            raise BadRequestException(f"Search query must be at least {min_length} characters.")
        resolved_locale = locale or getattr(request.state, "locale", "en") or "en"
        results = await products.search_published(
            q=q, locale=resolved_locale, limit=clamp_limit(limit)
        )
        return SearchOut.model_validate({"data": results})
