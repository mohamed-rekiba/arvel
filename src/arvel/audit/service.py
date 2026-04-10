"""AuditLog service — record and query audit entries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from arvel.audit.entry import AuditEntry
from arvel.audit.mixin import Auditable
from arvel.logging import Log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from arvel.audit.entry import AuditAction

logger = Log.named("arvel.audit")

REDACTED = "[REDACTED]"


class AuditLog:
    """Create and query audit trail entries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        action: AuditAction,
        model: Any,
        actor_id: str | None = None,
        old_values: dict[str, Any] | None = None,
        new_values: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Persist an audit entry for a model change."""
        model_type = type(model).__name__
        model_id = str(getattr(model, "id", ""))

        redact_fields: set[str] = set()
        if isinstance(model, Auditable):
            redact_fields = model.__audit_redact__

        entry = AuditEntry(
            actor_id=actor_id,
            action=action.value,
            model_type=model_type,
            model_id=model_id,
            old_values=_redact(old_values, redact_fields) if old_values else None,
            new_values=_redact(new_values, redact_fields) if new_values else None,
            timestamp=datetime.now(UTC),
        )
        self._session.add(entry)
        await self._session.flush()

        logger.info(
            "audit_recorded",
            action=action.value,
            model_type=model_type,
            model_id=model_id,
            actor_id=actor_id,
        )
        return entry

    async def for_model(self, model_type: type, model_id: int | str) -> list[AuditEntry]:
        """Query all audit entries for a specific model, ordered chronologically."""
        stmt = (
            select(AuditEntry)
            .where(
                AuditEntry.model_type == model_type.__name__,
                AuditEntry.model_id == str(model_id),
            )
            .order_by(AuditEntry.timestamp.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


def _redact(values: dict[str, Any], redact_fields: set[str]) -> dict[str, Any]:
    """Replace sensitive field values with a redaction marker."""
    if not redact_fields:
        return values
    return {k: REDACTED if k in redact_fields else v for k, v in values.items()}
