"""DatabaseChannel — persists notification to the notifications table."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

from arvel.logging.facade import Log
from arvel.notifications.notification import Notification

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_MAX_DATA_LEN = 65_535  # cap stored JSON payload size

logger = Log.channel(__name__)


class DatabaseChannel:
    """Inserts a DatabaseNotification row for each notification sent."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def send(self, notifiable: Any, notification: Notification) -> None:
        from arvel.notifications.models.database_notification import (
            DatabaseNotification,
        )

        data_dict = notification.to_database(notifiable)
        data_json = json.dumps(data_dict)
        if len(data_json) > _MAX_DATA_LEN:
            data_json = data_json[:_MAX_DATA_LEN]

        notifiable_id = str(getattr(notifiable, "id", "unknown"))
        notifiable_type = type(notifiable).__name__

        row = DatabaseNotification(
            id=str(uuid.uuid4()),
            type=f"{type(notification).__module__}.{type(notification).__qualname__}",
            notifiable_type=notifiable_type,
            notifiable_id=notifiable_id,
            data=data_json,
            read_at=None,
        )

        async with self._session_factory() as session:
            session.add(row)
            await session.commit()


__all__ = ["DatabaseChannel"]
