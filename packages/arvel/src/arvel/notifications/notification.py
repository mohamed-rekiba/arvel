"""Notification abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arvel.mail.mailable import Mailable

# Maps "module.ClassName" -> Notification subclass. Populated by __init_subclass__.
# Acts as the allowlist for deserializing queued notifications (NotificationJob).
NotificationRegistry: dict[str, type[Notification]] = {}


class Notification(ABC):
    """Base class for all notifications.

    Subclasses implement ``via(notifiable)`` returning a list of channel names.
    Optional: ``to_mail()``, ``to_database()``, ``to_broadcast()``.

    Subclasses auto-register in ``NotificationRegistry`` so queued notifications
    deserialize from an allowlist instead of importing arbitrary dotted paths.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        NotificationRegistry[f"{cls.__module__}.{cls.__qualname__}"] = cls

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


__all__ = ["Notification", "NotificationRegistry"]
