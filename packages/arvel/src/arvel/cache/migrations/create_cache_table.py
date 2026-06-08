"""Create cache table — database cache driver."""

from __future__ import annotations

from arvel.database import Blueprint, Schema

# Must match arvel.cache.stores.database.CacheEntry — the DatabaseStore reads these names.
__tablename__ = "cache_entries"


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _table(t: Blueprint) -> None:
        t.string("key", length=255).primary()
        t.text("value")
        t.integer("expires_at")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists(__tablename__)
