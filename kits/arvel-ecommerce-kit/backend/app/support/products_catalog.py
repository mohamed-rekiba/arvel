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


async def _execute_refresh() -> int:
    async with DB.autocommit() as conn:
        result = await conn.execute(_REFRESH_SQL)
        row = result.one_or_none()
    return int(row.cnt) if row else 0


async def refresh_products_catalog() -> int:
    """Refresh the products_catalog view once, guarded by the shared cache lock.

    Returns the number of rows in the catalog after refresh, or -1 if the lock
    was already held by another process. Used by the scheduler and write
    observers, where skipping a redundant refresh is fine — the next tick or
    write catches up.

    """
    async with Cache.lock(_REFRESH_LOCK, ttl=_REFRESH_LOCK_TTL_SECONDS) as acquired:
        if not acquired:
            return -1
        return await _execute_refresh()


async def refresh_products_catalog_now() -> int:
    """Refresh unconditionally — for the seeder, where skipping loses the data.

    No Redis lock: Postgres serializes a concurrent ``REFRESH ... CONCURRENTLY``
    on the same view via its own EXCLUSIVE lock (the second waits, it never
    errors or skips), so app-level coordination would only reintroduce the
    silent-skip bug.
    """
    return await _execute_refresh()


__all__ = ["refresh_products_catalog", "refresh_products_catalog_now"]
