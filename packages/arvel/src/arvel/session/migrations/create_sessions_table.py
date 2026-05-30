"""Create sessions table — database session driver."""

from __future__ import annotations

from arvel.database import Blueprint, Schema

__tablename__ = "sessions"


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _table(t: Blueprint) -> None:
        t.string("id", length=255).primary()
        t.big_integer("user_id").nullable()
        t.string("ip_address", length=45).nullable()
        t.text("user_agent").nullable()
        t.long_text("payload")
        t.integer("last_activity")
        t.index(["user_id"], name="sessions_user_id_idx")
        t.index(["last_activity"], name="sessions_last_activity_idx")

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists(__tablename__)
