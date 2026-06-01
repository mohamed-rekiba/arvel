"""OrderService — checkout and order lifecycle management."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, cast

from arvel.logging.facade import Log

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_catalog import ProductCatalog
from app.models.user import User
from app.services.cart_service import CartService


class OrderNotFoundError(Exception):
    pass


class EmptyCartError(Exception):
    pass


class InsufficientStockError(Exception):
    def __init__(self, product_id: str) -> None:
        super().__init__(product_id)
        self.product_id = product_id


class InvalidOrderStatusTransitionError(Exception):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"Cannot move order from {current!r} to {target!r}.")
        self.current = current
        self.target = target


class OrderService:
    def __init__(self) -> None:
        self._cart_service = CartService()

    @staticmethod
    def _parse_id(order_id: str) -> uuid.UUID | None:
        # Malformed path params should 404, not 500.
        try:
            return uuid.UUID(order_id)
        except ValueError:
            return None

    async def checkout(self, user_id: int, shipping_address: dict[str, Any]) -> dict[str, Any]:
        cart = await self._cart_service.get_cart_for_checkout(user_id)
        items = cart["items"]
        if not items:
            raise EmptyCartError("Cannot checkout with an empty cart.")

        Log.debug("order.placing", user_id=user_id, items=len(items))
        locked_products: dict[uuid.UUID, Product] = {}
        published_products: dict[uuid.UUID, ProductCatalog] = {}
        for item in items:
            pid = uuid.UUID(item["product_id"])
            published: ProductCatalog | None = await ProductCatalog.where(
                ProductCatalog.id == pid, ProductCatalog.real_status == "visible"
            ).first()
            if published is None or int(published.stock_qty) < item["quantity"]:
                raise InsufficientStockError(item["product_id"])
            published_products[pid] = published

            product: Product | None = (
                await Product.where(Product.id == pid).lock_for_update().first()
            )
            if product is None or int(product.stock_qty) < item["quantity"]:
                raise InsufficientStockError(item["product_id"])
            locked_products[pid] = product

        total = Decimal(str(cart["total"]))
        order: Order = await Order.create(
            user_id=user_id,
            status="pending",
            total=total,
            shipping_address=shipping_address,
        )

        for item in items:
            pid = uuid.UUID(item["product_id"])
            product = locked_products[pid]
            published = published_products[pid]
            name_data = published.name or {}
            name_snapshot = name_data.get("en", "")
            qty = item["quantity"]
            unit_price = Decimal(str(item["unit_price"]))

            await OrderItem.create(
                order_id=order.id,
                product_id=pid,
                product_name_snapshot=name_snapshot,
                quantity=qty,
                unit_price=unit_price,
                subtotal=unit_price * qty,
            )

            product.stock_qty = int(product.stock_qty) - qty
            await product.save()

        await self._cart_service.clear_cart(user_id)
        Log.debug("order.placed", order_id=str(order.id), total=float(total))

        result = await self.get_order(str(order.id), user_id)
        if result is None:
            raise OrderNotFoundError(str(order.id))
        return result

    async def list_orders(self, user_id: int) -> list[dict[str, Any]]:
        # Eager-load items in one batched query — no per-order line-item lookup.
        orders: list[Order] = (
            await Order.where(user_id=user_id).with_("items").order_by("-created_at").all()
        )
        results = []
        for o in orders:
            row = self._format_order(o)
            items = await o.items().get()
            row["items"] = self._format_items(items)
            results.append(row)
        return results

    async def get_order(self, order_id: str, user_id: int) -> dict[str, Any] | None:
        oid = self._parse_id(order_id)
        if oid is None:
            return None
        order: Order | None = (
            await Order.where(Order.id == oid, Order.user_id == user_id).with_("items").first()
        )
        if order is None:
            return None
        result = self._format_order(order)
        items = await order.items().get()
        result["items"] = self._format_items(items)
        return result

    async def admin_list_orders(
        self,
        *,
        user_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        # with_trashed() matches admin_get_order — soft-deleted orders stay visible for audit.
        qb = Order.with_trashed()
        if user_id is not None:
            qb = qb.where(user_id=user_id)
        if status is not None:
            qb = qb.where(status=status)
        total: int = await qb.count()
        # Eager-load items so the per-order formatter never re-queries.
        orders: list[Order] = (
            await qb.with_("items").order_by("-created_at").limit(limit).offset(offset).all()
        )
        user_ids = list({o.user_id for o in orders})
        users: list[User] = (
            await User.with_trashed().where(User.id.in_(user_ids)).all() if user_ids else []
        )
        user_map = {u.id: u for u in users}
        results = []
        for o in orders:
            row = self._format_order(o)
            items = await o.items().get()
            row["items"] = self._format_items(items)
            u = user_map.get(o.user_id)
            row["user"] = (
                {"id": u.id, "name": u.name, "email": u.email}
                if u
                else {"id": o.user_id, "name": "Unknown", "email": ""}
            )
            results.append(row)
        return {"data": results, "total": total}

    async def admin_get_order(self, order_id: str) -> dict[str, Any] | None:
        oid = self._parse_id(order_id)
        if oid is None:
            return None
        order: Order | None = (
            await Order.with_trashed().where(Order.id == oid).with_("items").first()
        )
        if order is None:
            return None
        result = self._format_order(order)
        items = await order.items().get()
        result["items"] = self._format_items(items)
        u: User | None = await User.with_trashed().where(User.id == order.user_id).first()
        result["user"] = (
            {"id": u.id, "name": u.name, "email": u.email}
            if u
            else {"id": order.user_id, "name": "Unknown", "email": ""}
        )
        return result

    async def best_sellers(self, *, limit: int = 5) -> list[dict[str, Any]]:
        # Build the CTE through the Order model's own query API.
        # .statement returns the raw Select without executing; global scopes (soft-delete)
        # are not applied there, so deleted_at IS NULL is added explicitly via where_null().
        valid_orders_cte = (
            Order.select("id")
            .where_null("deleted_at")
            .where(Order.status == "delivered")
            .statement.cte("valid_orders")
        )

        # _key_* strings mirror the exact select_raw expressions.
        # literal_column() uses the full expression text as the result dict key —
        # not the SQL AS alias — so key strings must match the SQL fragments exactly.
        _key_revenue = "SUM(subtotal) AS revenue"
        _key_units = "SUM(quantity) AS units_sold"

        # Single DB round-trip: join, aggregate, sort, limit — all at the DB level.
        # cast: join() is typed for model classes; CTE is a valid FromClause at runtime.
        rows: list[dict[str, Any]] = await (
            OrderItem.join(
                cast("type[Any]", valid_orders_cte), OrderItem.order_id == valid_orders_cte.c.id
            )
            .group_by("product_id", "product_name_snapshot")
            .select_raw(f"product_id, product_name_snapshot, {_key_revenue}, {_key_units}")
            .with_cte("valid_orders", valid_orders_cte)
            .order_by_raw("revenue DESC")
            .limit(limit)
            .all()
        )

        return [
            {
                "product_id": str(r["product_id"]) if r["product_id"] else None,
                "name": r["product_name_snapshot"] or "",
                "revenue": round(float(r[_key_revenue]), 2),
                "units_sold": int(r[_key_units]),
            }
            for r in rows
        ]

    async def update_status(self, order_id: str, status: str) -> dict[str, Any] | None:
        oid = self._parse_id(order_id)
        if oid is None:
            return None
        order: Order | None = await Order.with_trashed().where(Order.id == oid).first()
        if order is None:
            return None
        current_status = order.status or "pending"
        if not self._can_transition(current_status, status):
            raise InvalidOrderStatusTransitionError(current_status, status)
        Log.debug(
            "order.status.changing", order_id=order_id, from_status=current_status, to_status=status
        )
        if current_status != "cancelled" and status == "cancelled":
            await self._restore_stock_for_order(oid)
        order.status = status
        await order.save()
        Log.debug("order.status.changed", order_id=order_id, status=status)
        return await self.admin_get_order(order_id)

    async def _restore_stock_for_order(self, order_id: uuid.UUID) -> None:
        items: list[OrderItem] = await OrderItem.where(order_id=order_id).all()
        for item in items:
            if item.product_id is None:
                continue
            product: Product | None = (
                await Product.with_trashed()
                .where(Product.id == item.product_id)
                .lock_for_update()
                .first()
            )
            if product is None:
                continue
            product.stock_qty = int(product.stock_qty) + int(item.quantity)
            await product.save()

    @staticmethod
    def _can_transition(current: str, target: str) -> bool:
        if current == target:
            return True
        allowed: dict[str, set[str]] = {
            "pending": {"confirmed", "processing", "cancelled"},
            "confirmed": {"processing", "shipped", "cancelled"},
            "processing": {"shipped", "cancelled"},
            "shipped": {"delivered"},
            "delivered": set(),
            "cancelled": set(),
        }
        return target in allowed.get(current, set())

    @staticmethod
    def _format_items(items: list[OrderItem]) -> list[dict[str, Any]]:
        # Autoincrement id preserves insertion order — same ordering as the old
        # created_at sort, without re-querying the eager-loaded relation.
        ordered = sorted(items, key=lambda i: i.id)
        return [
            {
                "id": str(i.id),
                "product_id": str(i.product_id) if i.product_id else None,
                "product_name": i.product_name_snapshot,
                "quantity": int(i.quantity),
                "unit_price": float(i.unit_price),
                "subtotal": float(i.subtotal),
                "product": {"name": {"en": i.product_name_snapshot or ""}},
            }
            for i in ordered
        ]

    @staticmethod
    def _format_order(order: Order) -> dict[str, Any]:
        return {
            "id": str(order.id),
            "user_id": order.user_id,
            "status": order.status or "pending",
            "total": float(order.total or 0),
            "shipping_address": order.shipping_address or {},
            "created_at": order.created_at.isoformat() if order.created_at else None,
        }


__all__ = [
    "EmptyCartError",
    "InsufficientStockError",
    "InvalidOrderStatusTransitionError",
    "OrderNotFoundError",
    "OrderService",
]
