"""Database notification channel — persists rows to the notifications table."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import orjson

from arvel.notifications.contracts import NotificationChannel
from arvel.notifications.models import DatabaseNotification

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from arvel.notifications.notification import Notification


class DatabaseChannel(NotificationChannel):
    """Stores notification payloads using an async SQLAlchemy session."""

    def __init__(
        self,
        session_factory: Callable[..., Any],
    ) -> None:
        self._session_factory = session_factory

    async def deliver(self, notifiable: Any, notification: Notification) -> None:
        payload = notification.to_database(notifiable)
        record = DatabaseNotification(
            notifiable_type=type(notifiable).__name__,
            notifiable_id=notifiable.id,
            type=payload.type,
            data=orjson.dumps(payload.data).decode(),
        )
        session_ctx = self._session_factory()
        if inspect.isawaitable(session_ctx):
            session_ctx = await session_ctx
        async with session_ctx as session:
            session.add(record)
            await session.commit()
