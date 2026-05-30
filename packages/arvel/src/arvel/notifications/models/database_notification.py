"""DatabaseNotification ORM model — notifications table (FR-009-026)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from arvel.database.model import Model, Timestamps


class DatabaseNotification(Model, Timestamps):
    """Row in the ``notifications`` table.

    ``id`` is a UUID v4 string. ``notifiable_type`` + ``notifiable_id`` form
    a polymorphic FK (no DB constraint). ``data`` is JSON. ``read_at`` is NULL
    for unread notifications.
    """

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type: Mapped[str] = mapped_column(String(255), nullable=False)
    notifiable_type: Mapped[str] = mapped_column(String(255), nullable=False)
    notifiable_id: Mapped[str] = mapped_column(String(255), nullable=False)
    data: Mapped[str] = mapped_column(Text, nullable=False)
    # ``DatabaseChannel.send()`` writes ``datetime.now(UTC)`` (timezone-aware),
    # so the columns must be ``DateTime(timezone=True)``. SQLite ignores the
    # flag; Postgres / MySQL reject mixing aware and naive datetimes.
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


__all__ = ["DatabaseNotification"]
