"""arvel-audit — automatic audit trail and a fluent activity log for Arvel.

Add :class:`Auditable` to a model and every create/update/delete writes an
:class:`AuditEntry` in the same transaction. Log business events with
:func:`activity`, and read history back with :class:`AuditLog` /
:class:`ActivityQuery`.
"""

from __future__ import annotations

from arvel_audit.auditable import REDACTED, Auditable
from arvel_audit.commands import AuditInstallCommand
from arvel_audit.config import AuditConfig
from arvel_audit.exceptions import (
    AuditError,
    InvalidAuditAction,
    MissingActivityDescription,
)
from arvel_audit.models import AUDIT_ACTIONS, ActivityEntry, AuditEntry
from arvel_audit.provider import AuditServiceProvider
from arvel_audit.query import ActivityQuery, AuditLog
from arvel_audit.recorder import ActivityRecorder, activity
from arvel_audit.types import AuditValues

__all__ = [
    "AUDIT_ACTIONS",
    "REDACTED",
    "ActivityEntry",
    "ActivityQuery",
    "ActivityRecorder",
    "AuditConfig",
    "AuditEntry",
    "AuditError",
    "AuditInstallCommand",
    "AuditLog",
    "AuditServiceProvider",
    "AuditValues",
    "Auditable",
    "InvalidAuditAction",
    "MissingActivityDescription",
    "activity",
]
