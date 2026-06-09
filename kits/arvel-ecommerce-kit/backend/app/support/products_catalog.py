"""Products-catalog materialized-view maintenance."""

from __future__ import annotations

from arvel.database.db import DB
from arvel.facades.cache import Cache
from sqlalchemy import text

_REFRESH_LOCK = "ecommerce:products-catalog:refresh"
_REFRESH_LOCK_TTL_SECONDS = 600

# Pending-work flag. A write sets it before contending for the lock; the holder
# drains it. TTL is a safety net so a crash mid-drain can't pin it forever.
_REFRESH_DIRTY_KEY = "ecommerce:products-catalog:dirty"
_REFRESH_DIRTY_TTL_SECONDS = 3600

# REFRESH MATERIALIZED VIEW CONCURRENTLY is forbidden inside any transaction
# block. We run it on a dedicated autocommit connection so it's always outside.
_REFRESH_SQL = text("SELECT refresh_products_catalog() AS cnt")


async def _execute_refresh() -> int:
    async with DB.autocommit() as conn:
        result = await conn.execute(_REFRESH_SQL)
        row = result.one_or_none()
    return int(row.cnt) if row else 0


async def refresh_products_catalog() -> int:
    """Coalescing refresh of products_catalog, guarded by the shared cache lock.

    A plain lock-and-skip silently drops work: if a write commits while another
    refresh holds the lock, that write's refresh is dropped and the storefront
    stays stale until the next scheduler tick. Instead each caller sets a dirty
    flag before contending for the lock, and the holder drains it in a loop —
    clearing the flag right before each refresh, so a write landing mid-refresh
    re-sets it and forces another pass. Every committed write is followed by a
    refresh that started after it.

    Returns the row count of the last refresh this call ran, or -1 if another
    process already holds the lock (it will pick up our dirty flag and drain it).
    Used by the scheduler and write observers.
    """
    await Cache.put(_REFRESH_DIRTY_KEY, "1", ttl=_REFRESH_DIRTY_TTL_SECONDS)
    async with Cache.lock(_REFRESH_LOCK, ttl=_REFRESH_LOCK_TTL_SECONDS) as acquired:
        if not acquired:
            return -1
        count = -1
        # forget() returns True only while the flag is set: clear-then-refresh so
        # a concurrent write re-arms it and we loop once more to capture it.
        while await Cache.forget(_REFRESH_DIRTY_KEY):
            count = await _execute_refresh()
        return count


async def refresh_products_catalog_now() -> int:
    """Refresh unconditionally — for the seeder, where skipping loses the data.

    No Redis lock: Postgres serializes a concurrent ``REFRESH ... CONCURRENTLY``
    on the same view via its own EXCLUSIVE lock (the second waits, it never
    errors or skips), so app-level coordination would only reintroduce the
    silent-skip bug.
    """
    return await _execute_refresh()


__all__ = ["refresh_products_catalog", "refresh_products_catalog_now"]
