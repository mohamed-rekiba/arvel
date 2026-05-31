"""DatabaseNotification ORM model — notifications table (FR-009-026)."""

from __future__ import annotations

from datetime import datetime as _datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped

from arvel.database.columns import column, datetime, string, text
from arvel.database.model import Model, Timestamps


class DatabaseNotification(Model, Timestamps):
    """Row in the ``notifications`` table.

    ``id`` is a UUID v4 string. ``notifiable_type`` + ``notifiable_id`` form
    a polymorphic FK (no DB constraint). ``data`` is JSON. ``read_at`` is NULL
    for unread notifications.
    """

    __tablename__ = "notifications"

    id: Mapped[str] = column(String(36), primary_key=True)
    type: Mapped[str] = string(255)
    notifiable_type: Mapped[str] = string(255)
    notifiable_id: Mapped[str] = string(255)
    data: Mapped[str] = text()
    # ``DatabaseChannel.send()`` writes ``datetime.now(UTC)`` (timezone-aware),
    # so the column must be timezone-aware. SQLite ignores the flag; Postgres /
    # MySQL reject mixing aware and naive datetimes.
    read_at: Mapped[_datetime | None] = datetime(nullable=True, default=None)


__all__ = ["DatabaseNotification"]
