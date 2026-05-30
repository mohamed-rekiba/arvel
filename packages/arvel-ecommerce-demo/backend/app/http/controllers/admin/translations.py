"""Admin translations controller."""

from __future__ import annotations

from typing import Any

from app.http.controllers._deps import require_permission
from app.models.category import Category
from app.models.product import Product
from arvel.http import Request
from arvel.http.controller import Controller


class AdminTranslationsController(Controller):
    async def index(self, request: Request) -> dict[str, Any]:
        await require_permission(request, "categories.view")
        prods: list[Product] = await Product.order_by("created_at").limit(50).all()
        cats: list[Category] = await Category.order_by("created_at").limit(50).all()
        return {
            "data": [
                {
                    "model": "Product",
                    "id": str(p.id),
                    "fields": {
                        "name": p.name or {},
                        "slug": p.slug or {},
                        "description": p.description or {},
                    },
                }
                for p in prods
            ]
            + [
                {
                    "model": "Category",
                    "id": str(c.id),
                    "fields": {
                        "name": c.name or {},
                        "slug": c.slug or {},
                    },
                }
                for c in cats
            ]
        }
