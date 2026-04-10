"""Routes notifications to registered channels by name."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.logging import Log
from arvel.notifications.contracts import NotificationContract
from arvel.notifications.exceptions import NotificationChannelError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from arvel.notifications.contracts import NotificationChannel
    from arvel.notifications.notification import Notification

logger = Log.named("arvel.notifications.dispatcher")


class NotificationDispatcher(NotificationContract):
    """Dispatches a notification to concrete channels listed by ``notification.via()``."""

    def __init__(self, channels: Mapping[str, NotificationChannel]) -> None:
        self._channels = channels

    async def send(self, notifiable: Any, notification: Notification) -> None:
        for channel_name in notification.via():
            channel = self._channels.get(channel_name)
            if channel is None:
                logger.warning(
                    "Skipping unregistered notification channel %r",
                    channel_name,
                )
                continue
            try:
                await channel.deliver(notifiable, notification)
            except NotificationChannelError:
                raise
            except Exception as exc:
                raise NotificationChannelError(channel_name, str(exc)) from exc
