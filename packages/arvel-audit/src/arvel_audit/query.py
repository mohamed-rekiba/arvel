"""Read-side query builders for the audit trail and the activity log.

These are deliberately thin wrappers over SQLAlchemy ``select``. Access control
is the application's job — anything returned here is unredacted history.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Self

from arvel.database.paginator import Paginator
from sqlalchemy import ColumnElement, func, select

from arvel_audit._identity import model_key, morph_type
from arvel_audit.exceptions import InvalidAuditAction
from arvel_audit.models import AUDIT_ACTIONS, ActivityEntry, AuditEntry

if TYPE_CHECKING:
    from arvel.database.model import Model
    from sqlalchemy.ext.asyncio import AsyncSession


class AuditLog:
    """Query ``audit_entries`` by model, actor, action, and time window."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._filters: list[ColumnElement[bool]] = []

    def for_model(self, instance: Model) -> Self:
        self._filters.append(AuditEntry.model_type == morph_type(instance))
        self._filters.append(AuditEntry.model_id == model_key(instance))
        return self

    def by_actor(self, actor_id: object) -> Self:
        self._filters.append(AuditEntry.actor_id == str(actor_id))
        return self

    def action(self, action: str) -> Self:
        if action not in AUDIT_ACTIONS:
            raise InvalidAuditAction(action, AUDIT_ACTIONS)
        self._filters.append(AuditEntry.action == action)
        return self

    def since(self, moment: datetime) -> Self:
        self._filters.append(AuditEntry.created_at >= moment)
        return self

    def until(self, moment: datetime) -> Self:
        self._filters.append(AuditEntry.created_at <= moment)
        return self

    async def get(self) -> list[AuditEntry]:
        stmt = (
            select(AuditEntry)
            .where(*self._filters)
            .order_by(AuditEntry.created_at.asc(), AuditEntry.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def first(self) -> AuditEntry | None:
        stmt = (
            select(AuditEntry)
            .where(*self._filters)
            .order_by(AuditEntry.created_at.asc(), AuditEntry.id.asc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def count(self) -> int:
        stmt = select(func.count()).select_from(AuditEntry).where(*self._filters)
        return int((await self._session.execute(stmt)).scalar_one())

    async def paginate(self, *, per_page: int = 15, page: int = 1) -> Paginator[AuditEntry]:
        current = max(1, page)
        total = await self.count()
        stmt = (
            select(AuditEntry)
            .where(*self._filters)
            .order_by(AuditEntry.created_at.asc(), AuditEntry.id.asc())
            .offset((current - 1) * per_page)
            .limit(per_page)
        )
        result = await self._session.execute(stmt)
        items = list(result.scalars().all())
        return Paginator(items=items, total=total, per_page=per_page, current_page=current)


class ActivityQuery:
    """Query ``activity_entries`` by subject and causer."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._filters: list[ColumnElement[bool]] = []

    def in_log(self, log_name: str) -> Self:
        self._filters.append(ActivityEntry.log_name == log_name)
        return self

    def for_subject(self, instance: Model) -> Self:
        self._filters.append(ActivityEntry.subject_type == morph_type(instance))
        self._filters.append(ActivityEntry.subject_id == model_key(instance))
        return self

    def by_causer(self, instance: Model) -> Self:
        self._filters.append(ActivityEntry.causer_type == morph_type(instance))
        self._filters.append(ActivityEntry.causer_id == model_key(instance))
        return self

    async def get(self) -> list[ActivityEntry]:
        stmt = (
            select(ActivityEntry)
            .where(*self._filters)
            .order_by(ActivityEntry.created_at.asc(), ActivityEntry.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def first(self) -> ActivityEntry | None:
        stmt = (
            select(ActivityEntry)
            .where(*self._filters)
            .order_by(ActivityEntry.created_at.asc(), ActivityEntry.id.asc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def count(self) -> int:
        stmt = select(func.count()).select_from(ActivityEntry).where(*self._filters)
        return int((await self._session.execute(stmt)).scalar_one())


__all__ = ["ActivityQuery", "AuditLog"]
