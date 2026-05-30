"""Notification facade — classmethod API proxying to the bound NotificationManager."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from arvel.queue.exceptions import FacadeNotBoundError

if TYPE_CHECKING:
    from arvel.notifications.manager import NotificationManager
    from arvel.notifications.notification import Notification as _Notification


class Notification:
    """Facade for the notifications subsystem.

    Bound by ``NotificationServiceProvider.boot()``.
    """

    _manager: ClassVar[NotificationManager | None] = None

    @classmethod
    def bind(cls, manager: NotificationManager) -> None:
        cls._manager = manager

    @classmethod
    def reset(cls) -> None:
        """Unbind the manager (test teardown helper)."""
        cls._manager = None

    @classmethod
    def get_manager(cls) -> NotificationManager:
        if cls._manager is None:
            raise FacadeNotBoundError("Notification")
        return cls._manager

    @classmethod
    async def send(cls, notifiable: Any, notification: _Notification) -> None:
        await cls.get_manager().send(notifiable, notification)

    @classmethod
    async def send_now(cls, notifiable: Any, notification: _Notification) -> None:
        await cls.get_manager().send_now(notifiable, notification)


__all__ = ["Notification"]
