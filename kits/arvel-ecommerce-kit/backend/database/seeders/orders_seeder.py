"""Seed sample orders so the admin dashboard has revenue + best-seller data.

Without delivered orders the dashboard's best-sellers list and the 7-day
revenue series render empty. This seeds a handful of orders across the two
sample customers — mostly ``delivered`` (the only status ``best_sellers``
counts) plus one ``pending`` for KPI variety.

Idempotent: order ids are fixed literals (upsert on ``id``), and line items
are only inserted when the order has none yet — so ``db:seed`` re-runs cleanly.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from app.support.seeder import EcommerceSeeder

# Fixed order ids keep re-seeding idempotent. (product_slug, qty) per line.
_ORDERS: tuple[dict[str, Any], ...] = (
    {
        "id": "0193a000-0000-7000-8000-000000000001",
        "email": "customer@example.com",
        "status": "delivered",
        "days_ago": 1,
        "lines": (("iphone-15-pro", 2), ("airpods-pro-3", 1)),
    },
    {
        "id": "0193a000-0000-7000-8000-000000000002",
        "email": "customer2@example.com",
        "status": "delivered",
        "days_ago": 2,
        "lines": (("iphone-15-pro", 1), ("macbook-air-m4", 1)),
    },
    {
        "id": "0193a000-0000-7000-8000-000000000003",
        "email": "customer@example.com",
        "status": "delivered",
        "days_ago": 3,
        "lines": (("sony-wh-1000xm6", 3),),
    },
    {
        "id": "0193a000-0000-7000-8000-000000000004",
        "email": "customer2@example.com",
        "status": "delivered",
        "days_ago": 5,
        "lines": (("samsung-galaxy-s25", 2),),
    },
    {
        "id": "0193a000-0000-7000-8000-000000000005",
        "email": "customer@example.com",
        "status": "pending",
        "days_ago": 0,
        "lines": (("dell-xps-15", 1),),
    },
)

_SHIPPING = {
    "line1": "742 Evergreen Terrace",
    "city": "Springfield",
    "country": "US",
    "postal_code": "62704",
}


class OrdersSeeder(EcommerceSeeder):
    async def run(self) -> None:
        from app.models.order_item import OrderItem  # noqa: PLC0415
        from app.models.product import Product  # noqa: PLC0415

        for spec in _ORDERS:
            user = await self.db.table("users").where("email", spec["email"]).first()
            if user is None:
                continue

            # Resolve products + compute line totals up front so a missing
            # product skips the whole order rather than half-seeding it.
            lines: list[dict[str, Any]] = []
            total = Decimal(0)
            for slug, qty in spec["lines"]:
                product = await Product.where_json_path("slug", "en", slug).first()
                if product is None or product.price is None:
                    continue
                unit_price = Decimal(str(product.price))
                subtotal = unit_price * qty
                total += subtotal
                lines.append(
                    {
                        "product_id": str(product.id),
                        "product_name_snapshot": product.name["en"],
                        "quantity": qty,
                        "unit_price": str(unit_price),
                        "subtotal": str(subtotal),
                    }
                )
            if not lines:
                continue

            created_at = self.now() - timedelta(days=spec["days_ago"])
            await self.db.upsert(
                "orders",
                match_on=["id"],
                data={
                    "id": spec["id"],
                    "user_id": user["id"],
                    "status": spec["status"],
                    "total": str(total),
                    "shipping_address": _SHIPPING,
                    "created_at": created_at,
                    "updated_at": created_at,
                },
                cast_map={"id": "uuid", "status": "orders_status", "total": "numeric"},
            )

            order_uuid = uuid.UUID(spec["id"])
            if await OrderItem.where(OrderItem.order_id == order_uuid).count():
                continue
            for line in lines:
                await self.db.upsert(
                    "order_items",
                    match_on=[],
                    data={"order_id": spec["id"], **line},
                    cast_map={
                        "order_id": "uuid",
                        "product_id": "uuid",
                        "unit_price": "numeric",
                        "subtotal": "numeric",
                    },
                )
