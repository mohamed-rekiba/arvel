"""Observer that refreshes the products_catalog materialized view after commit."""

from __future__ import annotations

from typing import Any

from arvel.database.events import Observer

from app.support.products_catalog import refresh_products_catalog


class ProductsCatalogRefreshObserver(Observer[Any]):
    """Triggers a non-blocking view refresh after any Product, Category, or Vendor commit.

    Registered on all three models in AppServiceProvider so the materialized view
    stays consistent without scattering refresh calls across every route.

    """

    async def after_commit(self, _instance: Any) -> None:
        await refresh_products_catalog()


__all__ = ["ProductsCatalogRefreshObserver"]
