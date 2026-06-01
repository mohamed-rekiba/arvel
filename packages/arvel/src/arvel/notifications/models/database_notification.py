"""DatabaseNotification ORM model — notifications table."""

from __future__ import annotations

from datetime import datetime as _datetime

from arvel.database.columns import field, text
from arvel.database.model import Model, Timestamps


class DatabaseNotification(Model, Timestamps):
    """Row in the ``notifications`` table.

    ``id`` is a UUID v4 string. ``notifiable_type`` + ``notifiable_id`` form
    a polymorphic FK (no DB constraint). ``data`` is JSON. ``read_at`` is NULL
    for unread notifications.
    """

    __tablename__ = "notifications"

    id: str = field(length=36, primary_key=True)
    type: str
    notifiable_type: str
    notifiable_id: str
    data: str = text()
    # tz-aware: DatabaseChannel.send() writes datetime.now(UTC). SQLite ignores
    # the flag; Postgres/MySQL reject mixing aware and naive datetimes. The
    # datetime annotation maps to DateTime(timezone=True) via type_annotation_map.
    read_at: _datetime | None = None


__all__ = ["DatabaseNotification"]
