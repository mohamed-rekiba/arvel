"""Create cache table — database cache driver."""

from __future__ import annotations

from arvel.database import Blueprint, Schema

__tablename__ = "cache"


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _table(t: Blueprint) -> None:
        t.string("key", length=500).primary()
        t.text("value")
        t.integer("expiration")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists(__tablename__)
