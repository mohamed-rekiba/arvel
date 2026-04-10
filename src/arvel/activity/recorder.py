"""Fluent activity recorder and query helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from arvel.activity.entry import ActivityEntry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ActivityRecorder:
    """Fluent builder for creating activity log entries.

    Usage::

        await (
            activity("users", session=session)
            .log("logged_in")
            .by(user)
            .on(subject)
            .with_properties({"ip": "1.2.3.4"})
            .save()
        )
    """

    def __init__(self, log_name: str, *, session: AsyncSession) -> None:
        self._session = session
        self._log_name = log_name
        self._description: str = ""
        self._causer_type: str | None = None
        self._causer_id: str | None = None
        self._subject_type: str | None = None
        self._subject_id: str | None = None
        self._properties: dict[str, Any] | None = None

    def log(self, description: str) -> ActivityRecorder:
        self._description = description
        return self

    def by(self, causer: Any) -> ActivityRecorder:
        self._causer_type = type(causer).__name__
        self._causer_id = str(getattr(causer, "id", ""))
        return self

    def on(self, subject: Any) -> ActivityRecorder:
        self._subject_type = type(subject).__name__
        self._subject_id = str(getattr(subject, "id", ""))
        return self

    def with_properties(self, props: dict[str, Any]) -> ActivityRecorder:
        self._properties = props
        return self

    async def save(self) -> ActivityEntry:
        entry = ActivityEntry(
            log_name=self._log_name,
            description=self._description,
            subject_type=self._subject_type,
            subject_id=self._subject_id,
            causer_type=self._causer_type,
            causer_id=self._causer_id,
            properties=self._properties,
            timestamp=datetime.now(UTC),
        )
        self._session.add(entry)
        await self._session.flush()
        return entry


def activity(log_name: str, *, session: AsyncSession) -> ActivityRecorder:
    """Create a fluent activity recorder."""
    return ActivityRecorder(log_name, session=session)


class ActivityQuery:
    """Query helpers for activity entries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def for_subject(self, subject: Any) -> list[ActivityEntry]:
        stmt = (
            select(ActivityEntry)
            .where(
                ActivityEntry.subject_type == type(subject).__name__,
                ActivityEntry.subject_id == str(getattr(subject, "id", "")),
            )
            .order_by(ActivityEntry.timestamp.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def by_causer(self, causer: Any) -> list[ActivityEntry]:
        stmt = (
            select(ActivityEntry)
            .where(
                ActivityEntry.causer_type == type(causer).__name__,
                ActivityEntry.causer_id == str(getattr(causer, "id", "")),
            )
            .order_by(ActivityEntry.timestamp.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
