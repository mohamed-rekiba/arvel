"""NotificationFake + Notification.fake/.assert_* — recorder for tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import TracebackType
from typing import TYPE_CHECKING, Self, TypeVar

if TYPE_CHECKING:
    from arvel.facades.notification import NotificationManagerLike
    from arvel.notifications.notification import Notification

_N = TypeVar("_N", bound="Notification")


@dataclass(frozen=True)
class SentNotification:
    """One recorded send: who got it, and which notification."""

    notifiable: object
    notification: Notification


@dataclass
class NotificationFake:
    """In-memory NotificationManager — records every send, dispatches nothing.

    Mirrors Laravel's ``Notification::fake()``. Treats ``send`` and ``send_now``
    the same — both go straight into the buffer with no queueing or channel work.
    """

    sent: list[SentNotification] = field(default_factory=list[SentNotification])

    async def send(self, notifiable: object, notification: Notification) -> None:
        self.sent.append(SentNotification(notifiable, notification))

    async def send_now(self, notifiable: object, notification: Notification) -> None:
        self.sent.append(SentNotification(notifiable, notification))

    def sent_to(self, notifiable: object) -> list[SentNotification]:
        return [s for s in self.sent if s.notifiable is notifiable]

    def sent_of(self, notification_class: type[_N]) -> list[SentNotification]:
        return [s for s in self.sent if isinstance(s.notification, notification_class)]


class NotificationFakeContext:
    """Context manager: swap the bound NotificationManager with a fake."""

    def __init__(self) -> None:
        self._previous: NotificationManagerLike | None = None
        self.fake = NotificationFake()

    def __enter__(self) -> Self:
        from arvel.facades.notification import Notification

        self._previous = Notification.swap_manager(self.fake)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        from arvel.facades.notification import Notification

        Notification.swap_manager(self._previous)


__all__ = ["NotificationFake", "NotificationFakeContext", "SentNotification"]
