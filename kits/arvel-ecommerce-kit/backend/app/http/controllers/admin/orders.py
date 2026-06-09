"""Admin orders controller."""

from __future__ import annotations

from app.http.controllers._deps import orders, require_permission
from app.http.controllers._responses import (
    AdminOrderListOut,
    AdminOrderWrapperOut,
    BestSellersListOut,
    DashboardStatsOut,
)
from app.http.controllers._schemas import UpdateOrderStatusPayload
from app.services.order_service import InvalidOrderStatusTransitionError
from arvel.http import Request
from arvel.http.controller import Controller
from arvel.http.exceptions import NotFoundException, ValidationException


class AdminOrdersController(Controller):
    async def index(
        self,
        request: Request,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AdminOrderListOut:
        await require_permission(request, "orders.view")
        return AdminOrderListOut.model_validate(
            await orders.admin_list_orders(status=status, limit=limit, offset=offset)
        )

    async def best_sellers(self, request: Request, limit: int = 5) -> BestSellersListOut:
        await require_permission(request, "orders.view")
        data = await orders.best_sellers(limit=limit)
        return BestSellersListOut(data=data)

    async def stats(self, request: Request) -> DashboardStatsOut:
        await require_permission(request, "orders.view")
        return DashboardStatsOut.model_validate(await orders.dashboard_stats())

    async def show(self, order_id: str, request: Request) -> AdminOrderWrapperOut:
        await require_permission(request, "orders.view")
        order = await orders.admin_get_order(order_id)
        if order is None:
            raise NotFoundException("Order not found.")
        return AdminOrderWrapperOut.model_validate({"data": order})

    async def update_status(
        self, order_id: str, payload: UpdateOrderStatusPayload, request: Request
    ) -> AdminOrderWrapperOut:
        await require_permission(request, "orders.update")
        try:
            order = await orders.update_status(order_id, payload.status)
        except InvalidOrderStatusTransitionError as exc:
            raise ValidationException(str(exc)) from exc
        if order is None:
            raise NotFoundException("Order not found.")
        return AdminOrderWrapperOut.model_validate({"data": order})
