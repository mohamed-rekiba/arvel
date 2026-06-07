"""Notification facade — classmethod API proxying to the bound NotificationManager."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Protocol, TypeVar

from arvel.queue.exceptions import FacadeNotBoundError

if TYPE_CHECKING:
    from arvel.notifications.notification import Notification as _Notification
    from arvel.testing.fakes.notification import NotificationFake, NotificationFakeContext

_N = TypeVar("_N", bound="_Notification")


class NotificationManagerLike(Protocol):
    """Minimal surface the facade needs from its bound manager.

    Implemented by ``arvel.notifications.manager.NotificationManager`` (production)
    and ``arvel.testing.fakes.notification.NotificationFake`` (tests).
    """

    async def send(self, notifiable: Any, notification: _Notification) -> None: ...

    async def send_now(self, notifiable: Any, notification: _Notification) -> None: ...


class Notification:
    """Facade for the notifications subsystem.

    Bound by ``NotificationServiceProvider.boot()``.
    """

    _manager: ClassVar[NotificationManagerLike | None] = None

    @classmethod
    def bind(cls, manager: NotificationManagerLike) -> None:
        cls._manager = manager

    @classmethod
    def reset(cls) -> None:
        """Unbind the manager (test teardown helper)."""
        cls._manager = None

    @classmethod
    def swap_manager(cls, new: NotificationManagerLike | None) -> NotificationManagerLike | None:
        """Replace the bound manager, return the previous one. Test-only."""
        previous = cls._manager
        cls._manager = new
        return previous

    @classmethod
    def get_manager(cls) -> NotificationManagerLike:
        if cls._manager is None:
            raise FacadeNotBoundError("Notification")
        return cls._manager

    @classmethod
    async def send(cls, notifiable: Any, notification: _Notification) -> None:
        await cls.get_manager().send(notifiable, notification)

    @classmethod
    async def send_now(cls, notifiable: Any, notification: _Notification) -> None:
        await cls.get_manager().send_now(notifiable, notification)

    @classmethod
    def fake(cls) -> NotificationFakeContext:
        """Swap in a ``NotificationFake`` recorder for tests."""
        from arvel.testing.fakes.notification import NotificationFakeContext

        return NotificationFakeContext()

    @classmethod
    def _active_fake(cls, action: str) -> NotificationFake:
        from arvel.testing.fakes.notification import NotificationFake

        manager = cls._manager
        if not isinstance(manager, NotificationFake):
            raise TypeError(f"Notification.{action} requires Notification.fake() context")
        return manager

    @classmethod
    def assert_sent_to(
        cls,
        notifiable: Any,
        notification_class: type[_N],
        times: int | None = None,
    ) -> None:
        """Assert ``notifiable`` received an instance of ``notification_class``."""
        fake = cls._active_fake("assert_sent_to")
        matching = [
            s for s in fake.sent_to(notifiable) if isinstance(s.notification, notification_class)
        ]
        if not matching:
            raise AssertionError(
                f"Notification {notification_class.__qualname__!r} was not sent to {notifiable!r}"
            )
        if times is not None and len(matching) != times:
            raise AssertionError(
                f"Notification {notification_class.__qualname__!r} to {notifiable!r}: "
                f"expected {times}, got {len(matching)}"
            )

    @classmethod
    def assert_not_sent_to(cls, notifiable: Any, notification_class: type[_N]) -> None:
        """Assert ``notifiable`` did NOT receive ``notification_class``."""
        fake = cls._active_fake("assert_not_sent_to")
        matching = [
            s for s in fake.sent_to(notifiable) if isinstance(s.notification, notification_class)
        ]
        if matching:
            raise AssertionError(
                f"Notification {notification_class.__qualname__!r} was sent to "
                f"{notifiable!r} {len(matching)} time(s)"
            )

    @classmethod
    def assert_nothing_sent(cls) -> None:
        """Assert no notifications were sent at all."""
        fake = cls._active_fake("assert_nothing_sent")
        if fake.sent:
            raise AssertionError(f"{len(fake.sent)} notification(s) were sent")


__all__ = ["Notification", "NotificationManagerLike"]
