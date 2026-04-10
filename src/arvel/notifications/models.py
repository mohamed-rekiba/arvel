"""Notification ORM model — stores database-channel notifications."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column  # noqa: TC002

from arvel.data.model import ArvelModel


class DatabaseNotification(ArvelModel):
    """A notification stored in the database for the database channel.

    Columns classified as ``internal`` — no PII stored directly. The
    ``data`` column holds JSON-serialized notification payloads which
    must not contain credentials or raw PII.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notifiable_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    notifiable_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    data: Mapped[str] = mapped_column(Text, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
