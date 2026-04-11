"""Notification contract — ABC for multi-channel notification dispatch."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from arvel.notifications.notification import Notification


@runtime_checkable
class Notifiable(Protocol):
    """Any entity that can receive notifications (User, Team, etc.)."""

    def route_notification_for(self, channel: str) -> str | None:
        """Return the routing address for the given channel (email, phone, etc.)."""
        ...


class NotificationContract(ABC):
    """Abstract base class for the notification dispatcher.

    Routes notifications to multiple channels based on `notification.via()`.
    """

    @abstractmethod
    async def send(self, notifiable: Notifiable, notification: Notification) -> None:
        """Dispatch *notification* to *notifiable* through all channels returned by via()."""


class NotificationChannel(ABC):
    """Abstract base class for individual notification channels.

    Implementations: MailChannel, DatabaseChannel, SlackChannel.
    """

    @abstractmethod
    async def deliver(self, notifiable: Notifiable, notification: Notification) -> None:
        """Deliver the notification through this channel."""
