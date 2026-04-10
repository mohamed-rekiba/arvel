"""Failed job storage — SA model and repository for permanently failed jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column  # noqa: TC002

from arvel.data.model import ArvelModel


class FailedJob(ArvelModel):
    """Records jobs that exhausted all retry attempts."""

    __tablename__ = "failed_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_class: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    queue_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    exception_class: Mapped[str] = mapped_column(String(255), nullable=False)
    exception_message: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )


SENSITIVE_FIELD_PLACEHOLDER = "[REDACTED]"


def redact_payload(payload: dict[str, Any], sensitive_keys: frozenset[str]) -> dict[str, Any]:
    """Replace sensitive field values with a placeholder before storage."""
    redacted = dict(payload)
    for key in sensitive_keys:
        if key in redacted:
            redacted[key] = SENSITIVE_FIELD_PLACEHOLDER
    return redacted
