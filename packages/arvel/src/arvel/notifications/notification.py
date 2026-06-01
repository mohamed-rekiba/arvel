"""Notification abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arvel.mail.mailable import Mailable


class Notification(ABC):
    """Base class for all notifications.

    Subclasses implement ``via(notifiable)`` returning a list of channel names.
    Optional: ``to_mail()``, ``to_database()``, ``to_broadcast()``.
    """

    @abstractmethod
    def via(self, notifiable: Any) -> list[str]:
        """Return the list of channel names to send this notification through."""

    def to_mail(self, notifiable: Any) -> Mailable | None:
        """Return a Mailable for the mail channel, or None to skip."""
        return None

    def to_database(self, notifiable: Any) -> dict[str, Any]:
        """Return a dict for the database channel data field."""
        return {}

    def to_broadcast(self, notifiable: Any) -> dict[str, Any]:
        """Return a dict for the broadcast channel payload."""
        return {}


__all__ = ["Notification"]
