"""Account controller: customer order history."""

from __future__ import annotations

from app.http.controllers._deps import orders, require_auth
from app.http.controllers._responses import OrderListOut, OrderWrapperOut
from arvel.http import Request
from arvel.http.controller import Controller
from arvel.http.exceptions import NotFoundException


class AccountController(Controller):
    async def list_orders(self, request: Request) -> OrderListOut:
        user = await require_auth(request)
        return OrderListOut.model_validate({"data": await orders.list_orders(int(user.id))})

    async def show_order(self, order_id: str, request: Request) -> OrderWrapperOut:
        user = await require_auth(request)
        order = await orders.get_order(order_id, int(user.id))
        if order is None:
            raise NotFoundException("Order not found.")
        return OrderWrapperOut.model_validate({"data": order})
