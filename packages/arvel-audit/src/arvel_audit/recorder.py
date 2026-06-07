"""Fluent activity recorder for business events.

await activity("exports", session=db).log("Exported Q1 report").by(user).on(report).save()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from arvel_audit._identity import model_key, morph_type
from arvel_audit.auditable import Auditable
from arvel_audit.exceptions import MissingActivityDescription
from arvel_audit.models import ActivityEntry

if TYPE_CHECKING:
    from arvel.database.model import Model
    from sqlalchemy.ext.asyncio import AsyncSession


class ActivityRecorder:
    """Build and persist a single ``ActivityEntry`` with a fluent chain."""

    def __init__(self, log_name: str, *, session: AsyncSession) -> None:
        self._log_name = log_name
        self._session = session
        self._description: str | None = None
        self._subject: Model | None = None
        self._causer: Model | None = None
        self._properties: dict[str, Any] = {}

    def log(self, description: str) -> Self:
        self._description = description
        return self

    def by(self, causer: Model) -> Self:
        self._causer = causer
        return self

    def on(self, subject: Model) -> Self:
        self._subject = subject
        return self

    def with_properties(self, properties: dict[str, Any]) -> Self:
        self._properties.update(properties)
        return self

    def _safe_properties(self) -> dict[str, Any]:
        # A subject's redacted columns must never bleed into the activity log.
        # Widen to object first: the SQLAlchemy plugin types _subject as a
        # concrete Model, so mypy would otherwise call the Auditable branch
        # unreachable even though subjects routinely mix both in.
        subject: object = self._subject
        if not isinstance(subject, Auditable):
            return dict(self._properties)
        redacted = subject.audit_redacted_fields()
        return {k: v for k, v in self._properties.items() if k not in redacted}

    async def save(self) -> ActivityEntry:
        if self._description is None:
            raise MissingActivityDescription
        entry = ActivityEntry(
            log_name=self._log_name,
            description=self._description,
            subject_type=morph_type(self._subject) if self._subject is not None else None,
            subject_id=model_key(self._subject) if self._subject is not None else None,
            causer_type=morph_type(self._causer) if self._causer is not None else None,
            causer_id=model_key(self._causer) if self._causer is not None else None,
            properties=self._safe_properties(),
        )
        self._session.add(entry)
        await self._session.flush()
        return entry


def activity(log_name: str = "default", *, session: AsyncSession) -> ActivityRecorder:
    """Start an activity record in ``log_name`` bound to ``session``."""
    return ActivityRecorder(log_name, session=session)


__all__ = ["ActivityRecorder", "activity"]
