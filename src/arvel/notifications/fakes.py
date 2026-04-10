"""NotificationFake — testing double that captures notifications for assertion."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.notifications.contracts import NotificationContract

if TYPE_CHECKING:
    from arvel.notifications.notification import Notification


class NotificationFake(NotificationContract):
    """Captures all sent notifications for test assertions."""

    def __init__(self) -> None:
        self._sent: list[tuple[Any, Notification]] = []

    @property
    def sent_count(self) -> int:
        return len(self._sent)

    async def send(self, notifiable: Any, notification: Notification) -> None:
        self._sent.append((notifiable, notification))

    def assert_sent_to(
        self,
        notifiable: Any,
        notification_type: type[Notification] | None = None,
    ) -> None:
        for n, notif in self._sent:
            type_match = notification_type is None or isinstance(notif, notification_type)
            if n == notifiable and type_match:
                return
        if notification_type is not None:
            msg = f"Expected {notification_type.__name__} sent to '{notifiable}', but none found"
        else:
            msg = f"Expected notification sent to '{notifiable}', but none found"
        raise AssertionError(msg)

    def assert_nothing_sent(self) -> None:
        if self._sent:
            msg = f"Expected no notifications, but got {len(self._sent)}"
            raise AssertionError(msg)

    def assert_sent_type(self, notification_type: type[Notification]) -> None:
        for _, n in self._sent:
            if isinstance(n, notification_type):
                return
        msg = f"Expected {notification_type.__name__} to be sent, but it wasn't"
        raise AssertionError(msg)
