"""Scheduler registration for the ecommerce demo."""

from __future__ import annotations

from arvel.scheduling import Schedule

from app.support.products_catalog import refresh_products_catalog


async def refresh_products_catalog_schedule() -> None:
    await refresh_products_catalog()


class Kernel:
    """Application schedule definitions."""

    def schedule(self, schedule: Schedule) -> None:
        (
            schedule.call(refresh_products_catalog_schedule)
            .name("products-catalog.refresh")
            .description("Refresh the storefront materialized view")
            .everyTenMinutes()
            .withoutOverlapping(ttl_minutes=10)
            .onOneServer(ttl_seconds=60)
        )
        # Prune abandoned carts (30 days idle, see Cart.prunable_query).
        schedule.command("model:prune").daily().at("02:00")


__all__ = ["Kernel", "refresh_products_catalog_schedule"]
