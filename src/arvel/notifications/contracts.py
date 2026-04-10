"""Notification contract — ABC for multi-channel notification dispatch."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arvel.notifications.notification import Notification


class NotificationContract(ABC):
    """Abstract base class for the notification dispatcher.

    Routes notifications to multiple channels based on `notification.via()`.
    """

    @abstractmethod
    async def send(self, notifiable: Any, notification: Notification) -> None:
        """Dispatch *notification* to *notifiable* through all channels returned by via()."""


class NotificationChannel(ABC):
    """Abstract base class for individual notification channels.

    Implementations: MailChannel, DatabaseChannel, SlackChannel.
    """

    @abstractmethod
    async def deliver(self, notifiable: Any, notification: Notification) -> None:
        """Deliver the notification through this channel."""
