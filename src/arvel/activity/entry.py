"""ActivityEntry model — stores a single activity log record."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column  # noqa: TC002

from arvel.data.model import ArvelModel


class ActivityEntry(ArvelModel):
    """User-facing activity log entry.

    Unlike audit entries, activity records are manually recorded,
    user-facing, and subject to retention policies.
    """

    __tablename__ = "activity_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    log_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    subject_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    causer_type: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    causer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    properties: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
