"""Notifiable mixin — adds notify() and notify_now() to ORM models (FR-009-024)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.notifications.manager import NotificationManager
    from arvel.notifications.notification import Notification


class Notifiable:
    """Mixin that adds ``notify()`` and ``notify_now()`` to any class.

    Requires only ``self.id`` and ``self.__class__.__name__`` (duck-typed).
    ``notification_manager`` is injected in tests; in production it is resolved
    from the NotificationManager bound in the container.
    """

    notification_manager: NotificationManager | None = None

    def _get_manager(self) -> NotificationManager:
        if self.notification_manager is not None:
            return self.notification_manager
        from arvel.facades.notification import Notification as NotificationFacade

        return NotificationFacade.get_manager()

    async def notify(self, notification: Notification) -> None:
        """Send the notification — queued if notification implements ShouldQueue."""
        from arvel.notifications.should_queue import ShouldQueue

        manager = self._get_manager()
        if isinstance(notification, ShouldQueue):
            await manager.send_via_queue(self, notification)
        else:
            await manager.send(self, notification)

    async def notify_now(self, notification: Notification) -> None:
        """Send the notification synchronously, bypassing any queue."""
        await self._get_manager().send_now(self, notification)


__all__ = ["Notifiable"]
