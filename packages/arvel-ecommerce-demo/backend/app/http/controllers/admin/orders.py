"""Admin orders controller."""

from __future__ import annotations

from typing import Any

from app.http.controllers._deps import orders, require_permission
from app.http.controllers._responses import BestSellersListOut
from app.http.controllers._schemas import UpdateOrderStatusPayload
from app.services.order_service import InvalidOrderStatusTransitionError
from arvel.http.controller import Controller
from arvel.http.exceptions import NotFoundException, ValidationException
from pydantic import ValidationError
from starlette.requests import Request


class AdminOrdersController(Controller):
    async def index(
        self,
        request: Request,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        await require_permission(request, "orders.view")
        return await orders.admin_list_orders(status=status, limit=limit, offset=offset)

    async def best_sellers(self, request: Request, limit: int = 5) -> BestSellersListOut:
        await require_permission(request, "orders.view")
        data = await orders.best_sellers(limit=limit)
        return BestSellersListOut(data=data)

    async def show(self, order_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "orders.view")
        order = await orders.admin_get_order(order_id)
        if order is None:
            raise NotFoundException("Order not found.")
        return {"data": order}

    async def update_status(self, order_id: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "orders.update")
        try:
            payload = UpdateOrderStatusPayload.model_validate(await request.json())
        except ValidationError as exc:
            raise ValidationException(str(exc)) from exc
        try:
            order = await orders.update_status(order_id, payload.status)
        except InvalidOrderStatusTransitionError as exc:
            raise ValidationException(str(exc)) from exc
        if order is None:
            raise NotFoundException("Order not found.")
        return {"data": order}
