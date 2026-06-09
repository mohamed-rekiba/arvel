"""Checkout controller."""

from __future__ import annotations

from app.http.controllers._deps import orders, require_auth
from app.http.controllers._responses import OrderWrapperOut
from app.http.controllers._schemas import CheckoutPayload
from app.services.order_service import EmptyCartError, InsufficientStockError
from arvel.http import Request
from arvel.http.controller import Controller
from arvel.http.exceptions import ConflictException, ValidationException


class CheckoutController(Controller):
    async def checkout(self, payload: CheckoutPayload, request: Request) -> OrderWrapperOut:
        user = await require_auth(request)
        resolved_locale = getattr(request.state, "locale", "en") or "en"
        try:
            order = await orders.checkout(
                int(user.id), payload.shipping_address, locale=resolved_locale
            )
        except EmptyCartError as exc:
            raise ValidationException("Cart is empty.") from exc
        except InsufficientStockError as exc:
            raise ConflictException(
                "Insufficient stock.",
                details=[{"field": "product_id", "issue": exc.product_id}],
            ) from exc
        return OrderWrapperOut.model_validate({"data": order})
