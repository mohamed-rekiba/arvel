"""Audit and activity tables.

``AuditEntry`` is the automatic change trail written by ``AuditObserver``.
``ActivityEntry`` is the business-event log written by ``ActivityRecorder``.
"""

from __future__ import annotations

from datetime import datetime as _datetime
from typing import Any, ClassVar

from arvel.database import column, datetime, id_, json, string
from arvel.database.model import Model
from sqlalchemy import Index
from sqlalchemy.orm import Mapped

from arvel_audit.config import AuditConfig
from arvel_audit.types import AuditValues

# Resolved once: whether old/new value blobs are encrypted at rest. Reading env
# at import is fine — the column type is fixed for the table's lifetime.
_ENCRYPT_VALUES = AuditConfig().encrypt_values

AUDIT_ACTIONS: tuple[str, ...] = ("created", "updated", "deleted")


class AuditEntry(Model):
    """One recorded create/update/delete on an audited model."""

    __tablename__ = "audit_entries"
    __table_args__ = (Index("audit_entries_model_idx", "model_type", "model_id"),)
    # Append-only: created_at is auto-set on insert; there is no updated_at.
    UPDATED_AT: ClassVar[str] = ""

    id: Mapped[int] = id_(init=False)
    action: Mapped[str] = string(20)
    model_type: Mapped[str] = string(255)
    model_id: Mapped[str] = string(64)
    old_values: Mapped[dict[str, Any]] = column(AuditValues(encrypt=_ENCRYPT_VALUES))
    new_values: Mapped[dict[str, Any]] = column(AuditValues(encrypt=_ENCRYPT_VALUES))
    actor_id: Mapped[str | None] = string(64, nullable=True)
    created_at: Mapped[_datetime] = datetime(nullable=False, init=False, default=None)


class ActivityEntry(Model):
    """One business-level activity (Spatie ActivityLog parity)."""

    __tablename__ = "activity_entries"
    __table_args__ = (
        Index("activity_entries_subject_idx", "subject_type", "subject_id"),
        Index("activity_entries_causer_idx", "causer_type", "causer_id"),
    )
    UPDATED_AT: ClassVar[str] = ""

    id: Mapped[int] = id_(init=False)
    log_name: Mapped[str] = string(100)
    description: Mapped[str] = string(2000)
    subject_type: Mapped[str | None] = string(255, nullable=True)
    subject_id: Mapped[str | None] = string(64, nullable=True)
    causer_type: Mapped[str | None] = string(255, nullable=True)
    causer_id: Mapped[str | None] = string(64, nullable=True)
    properties: Mapped[dict[str, Any]] = json()
    created_at: Mapped[_datetime] = datetime(nullable=False, init=False, default=None)


__all__ = ["AUDIT_ACTIONS", "ActivityEntry", "AuditEntry"]
