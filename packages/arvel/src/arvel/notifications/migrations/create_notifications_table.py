"""Create notifications table — database notification channel.

Schema decisions:

- ``id`` is a UUID v4 string (VARCHAR 36) — stable reference for mark-as-read.
- ``type`` stores the fully-qualified notification class name.
- ``notifiable_type`` + ``notifiable_id`` form a polymorphic FK (no real FK
  — notifiable can be any model).
- ``data`` TEXT stores JSON payload from ``to_database()``.
- ``read_at`` is NULL for unread notifications; set when the user reads them.
- Composite index on ``(notifiable_type, notifiable_id, read_at)``
  optimises "fetch all unread notifications for user X".
"""

from __future__ import annotations

from arvel.database import Blueprint, Schema

__tablename__ = "notifications"


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _table(t: Blueprint) -> None:
        t.string("id", length=36).primary()
        t.string("type", length=255)
        t.string("notifiable_type", length=255)
        t.string("notifiable_id", length=255)
        t.text("data")
        t.datetime("read_at").nullable()
        t.timestamps()
        t.index(
            ["notifiable_type", "notifiable_id", "read_at"],
            name="notifications_notifiable_read_idx",
        )

    schema.create(__tablename__, _table)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists(__tablename__)
