"""Cart controller: view, add, update, and remove items."""

from __future__ import annotations

from app.http.controllers._deps import carts, require_auth
from app.http.controllers._responses import CartWrapperOut
from app.http.controllers._schemas import AddCartItemPayload, UpdateCartItemPayload
from arvel.http import Request
from arvel.http.controller import Controller


class CartController(Controller):
    async def show(self, request: Request, locale: str | None = None) -> CartWrapperOut:
        user = await require_auth(request)
        resolved_locale = locale or getattr(request.state, "locale", "en") or "en"
        return CartWrapperOut.model_validate(
            {"data": await carts.get_cart(int(user.id), locale=resolved_locale)}
        )

    async def add_item(
        self, payload: AddCartItemPayload, request: Request, locale: str | None = None
    ) -> CartWrapperOut:
        user = await require_auth(request)
        resolved_locale = locale or getattr(request.state, "locale", "en") or "en"
        return CartWrapperOut.model_validate(
            {
                "data": await carts.add_item(
                    int(user.id), payload.product_id, payload.quantity, locale=resolved_locale
                )
            }
        )

    async def update_item(
        self,
        item_id: str,
        payload: UpdateCartItemPayload,
        request: Request,
        locale: str | None = None,
    ) -> CartWrapperOut:
        user = await require_auth(request)
        resolved_locale = locale or getattr(request.state, "locale", "en") or "en"
        return CartWrapperOut.model_validate(
            {
                "data": await carts.update_item(
                    int(user.id), item_id, payload.quantity, locale=resolved_locale
                )
            }
        )

    async def remove_item(
        self, item_id: str, request: Request, locale: str | None = None
    ) -> CartWrapperOut:
        user = await require_auth(request)
        resolved_locale = locale or getattr(request.state, "locale", "en") or "en"
        return CartWrapperOut.model_validate(
            {"data": await carts.remove_item(int(user.id), item_id, locale=resolved_locale)}
        )
