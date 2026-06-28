"""The ``database`` notification channel's storage model (Laravel parity).

``DatabaseNotification`` is an arvel ``Model`` backing the ``notifications`` table — a UUID-keyed row
per delivered notification (``type`` + the polymorphic ``notifiable_type``/``notifiable_id`` + a JSON
``data`` payload + a nullable ``read_at``). Kept in its own module so importing the rest of
``arvel.notifications`` (the in-memory channels) doesn't pull in ``arvel.database``/SQLAlchemy.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Self

from arvel.database import HasUuids, Model


class DatabaseNotification(HasUuids, Model):
    """A stored notification row. UUID primary key; ``data`` is JSON; ``read_at`` is null until read."""

    __table_name__ = "notifications"
    # NB: the `data`/`read_at` casts serialize to strings themselves (JSON text / ISO datetime — arvel's
    # standard storage, like created_at/updated_at), so the scaffold migration's TEXT/DATETIME columns
    # and these field types are intentionally cast-compatible, not drift. Don't "fix" the mismatch.
    __fields__: ClassVar[dict[str, type]] = {
        "type": str,
        "notifiable_type": str,
        "notifiable_id": str,
        "data": dict,
        "read_at": datetime,
    }
    __fillable__: ClassVar[list[str]] = [
        "type",
        "notifiable_type",
        "notifiable_id",
        "data",
        "read_at",
    ]
    __casts__: ClassVar[dict[str, Any]] = {"data": "json", "read_at": "datetime"}
    __timestamps__ = True

    # Dynamic column (stored in _attributes via the datetime cast) — annotated so the type checker
    # accepts both the Date stamp and the None reset below; not a real class attribute.
    read_at: Any

    @property
    def read(self) -> bool:
        return self.read_at is not None

    @property
    def unread(self) -> bool:
        return self.read_at is None

    async def mark_as_read(self) -> Self:
        """Stamp ``read_at`` now (idempotent) and persist."""
        if self.read_at is None:
            from arvel.dates import Date

            self.read_at = Date.now()
            await self.save()
        return self

    async def mark_as_unread(self) -> Self:
        """Clear ``read_at`` (idempotent) and persist."""
        if self.read_at is not None:
            self.read_at = None
            await self.save()
        return self
