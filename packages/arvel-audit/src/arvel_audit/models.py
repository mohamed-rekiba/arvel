"""Audit and activity tables.

``AuditEntry`` is the automatic change trail written by ``AuditObserver``.
``ActivityEntry`` is the business-event log written by ``ActivityRecorder``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from arvel.database.model import Model
from sqlalchemy import JSON, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from arvel_audit.config import AuditConfig
from arvel_audit.types import AuditValues

# Resolved once: whether old/new value blobs are encrypted at rest. Reading env
# at import is fine — the column type is fixed for the table's lifetime.
_ENCRYPT_VALUES = AuditConfig().encrypt_values

AUDIT_ACTIONS: tuple[str, ...] = ("created", "updated", "deleted")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AuditEntry(Model):
    """One recorded create/update/delete on an audited model."""

    __tablename__ = "audit_entries"
    __table_args__ = (Index("audit_entries_model_idx", "model_type", "model_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False, autoincrement=True, default=None)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    model_type: Mapped[str] = mapped_column(String(255), nullable=False)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    old_values: Mapped[dict[str, Any]] = mapped_column(AuditValues(encrypt=_ENCRYPT_VALUES))
    new_values: Mapped[dict[str, Any]] = mapped_column(AuditValues(encrypt=_ENCRYPT_VALUES))
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, default_factory=_utcnow
    )


class ActivityEntry(Model):
    """One business-level activity (Spatie ActivityLog parity)."""

    __tablename__ = "activity_entries"
    __table_args__ = (
        Index("activity_entries_subject_idx", "subject_type", "subject_id"),
        Index("activity_entries_causer_idx", "causer_type", "causer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, init=False, autoincrement=True, default=None)
    log_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    subject_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    causer_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    causer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, default_factory=_utcnow
    )


__all__ = ["AUDIT_ACTIONS", "ActivityEntry", "AuditEntry"]
