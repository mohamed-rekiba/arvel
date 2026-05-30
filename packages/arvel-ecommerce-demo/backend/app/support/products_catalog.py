"""Products-catalog materialized-view maintenance."""

from __future__ import annotations

from arvel.database.db import DB
from arvel.facades.cache import Cache
from sqlalchemy import text

_REFRESH_LOCK = "ecommerce:products-catalog:refresh"
_REFRESH_LOCK_TTL_SECONDS = 600

# REFRESH MATERIALIZED VIEW CONCURRENTLY is forbidden inside any transaction
# block. We run it on a dedicated autocommit connection so it's always outside.
_REFRESH_SQL = text("SELECT refresh_products_catalog() AS cnt")


async def refresh_products_catalog() -> int:
    """Refresh the products_catalog view once, guarded by the shared cache lock.

    Returns the number of rows in the catalog after refresh, or -1 if the lock
    was already held by another process.
    """
    async with Cache.lock(_REFRESH_LOCK, ttl=_REFRESH_LOCK_TTL_SECONDS) as acquired:
        if not acquired:
            return -1
        async with DB.autocommit() as conn:
            result = await conn.execute(_REFRESH_SQL)
            row = result.one_or_none()
        return int(row.cnt) if row else 0


__all__ = ["refresh_products_catalog"]
