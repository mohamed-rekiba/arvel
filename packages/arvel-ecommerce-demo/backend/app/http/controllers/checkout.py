"""Checkout controller."""

from __future__ import annotations

from typing import Any

from app.http.controllers._deps import orders, require_auth
from app.http.controllers._schemas import CheckoutPayload
from app.services.order_service import EmptyCartError, InsufficientStockError
from arvel.http.controller import Controller
from arvel.http.exceptions import ConflictException, ValidationException
from starlette.requests import Request


class CheckoutController(Controller):
    async def checkout(self, payload: CheckoutPayload, request: Request) -> dict[str, Any]:
        user = await require_auth(request)
        try:
            order = await orders.checkout(int(user.id), payload.shipping_address)
        except EmptyCartError as exc:
            raise ValidationException("Cart is empty.") from exc
        except InsufficientStockError as exc:
            raise ConflictException(
                "Insufficient stock.",
                details=[{"field": "product_id", "issue": exc.product_id}],
            ) from exc
        return {"data": order}
