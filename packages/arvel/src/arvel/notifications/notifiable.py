"""Notifiable mixin — adds notify and notify_now to ORM models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from arvel.notifications.manager import NotificationManager
    from arvel.notifications.notification import Notification

# Maps "module.ClassName" -> Notifiable subclass. Populated by __init_subclass__.
# Allowlist for resolving the notifiable in a queued NotificationJob — the worker
# never imports the dotted path from the (untrusted) queue payload.
NotifiableRegistry: dict[str, type[Notifiable]] = {}


class Notifiable:
    """Mixin that adds ``notify()`` and ``notify_now()`` to any class.

    Requires only ``self.id`` and ``self.__class__.__name__`` (duck-typed).
    ``notification_manager`` is injected in tests; in production it is resolved
    from the NotificationManager bound in the container.

    Subclasses auto-register in ``NotifiableRegistry`` so queued notifications
    resolve the notifiable from an allowlist instead of importing arbitrary paths.
    """

    notification_manager: NotificationManager | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        NotifiableRegistry[f"{cls.__module__}.{cls.__qualname__}"] = cls

    def _get_manager(self) -> NotificationManager:
        if self.notification_manager is not None:
            return self.notification_manager
        from arvel.facades.notification import Notification as NotificationFacade

        # The facade is bound with a concrete NotificationManager in production.
        # The Protocol return type exists so tests can bind a fake without
        # subclassing the manager.
        return cast("NotificationManager", NotificationFacade.get_manager())

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


__all__ = ["Notifiable", "NotifiableRegistry"]
