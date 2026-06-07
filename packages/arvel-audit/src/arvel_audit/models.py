"""Audit and activity tables.

``AuditEntry`` is the automatic change trail written by ``AuditObserver``.
``ActivityEntry`` is the business-event log written by ``ActivityRecorder``.
"""

from __future__ import annotations

from datetime import datetime as _datetime
from typing import Any, ClassVar

from arvel.database import column, field, json
from arvel.database.model import Model
from sqlalchemy import Index

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

    id: int = field(default=None, primary_key=True, init=False)
    action: str = field(length=20)
    model_type: str
    model_id: str = field(length=64)
    old_values: dict[str, Any] = column(AuditValues(encrypt=_ENCRYPT_VALUES))
    new_values: dict[str, Any] = column(AuditValues(encrypt=_ENCRYPT_VALUES))
    actor_id: str | None = field(length=64)
    created_at: _datetime = field(init=False, default=None)


class ActivityEntry(Model):
    """One business-level activity record."""

    __tablename__ = "activity_entries"
    __table_args__ = (
        Index("activity_entries_subject_idx", "subject_type", "subject_id"),
        Index("activity_entries_causer_idx", "causer_type", "causer_id"),
    )
    UPDATED_AT: ClassVar[str] = ""

    id: int = field(default=None, primary_key=True, init=False)
    log_name: str = field(length=100)
    description: str = field(length=2000)
    subject_type: str | None
    subject_id: str | None = field(length=64)
    causer_type: str | None
    causer_id: str | None = field(length=64)
    properties: dict[str, Any] = json()
    created_at: _datetime = field(init=False, default=None)


__all__ = ["AUDIT_ACTIONS", "ActivityEntry", "AuditEntry"]
