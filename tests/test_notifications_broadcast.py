"""Notifications (spec 19 §3) — the ``broadcast`` channel + the ``should_send`` gate."""

from __future__ import annotations

from typing import Any

from arvel.broadcasting import BroadcastManager, LogBroadcaster
from arvel.notifications import BroadcastNotification, Notifiable, Notification, NotificationManager


class OrderShipped(Notification):
    def __init__(self, order_id: int) -> None:
        self.order_id = order_id

    def via(self, notifiable: Any) -> list[str]:
        return ["mail", "database", "broadcast"]

    def to_mail(self, notifiable: Any) -> Any:
        from arvel.mail import Mailable

        return Mailable().subject("Shipped").html("<p>on its way</p>")

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"order_id": self.order_id}


class User(Notifiable):
    def __init__(self, user_id: int) -> None:
        self.id = user_id


def test_notification_base_defaults_include_should_send_and_to_broadcast() -> None:
    note = Notification()
    assert note.should_send(object(), "mail") is True
    assert note.to_broadcast(object()) == {}  # defaults to to_array()


class _FakeApp:
    """Minimal container stub: only "broadcast" is bound, resolving to ``manager``."""

    def __init__(self, manager: BroadcastManager) -> None:
        self._manager = manager

    def bound(self, name: str) -> bool:
        return name == "broadcast"

    def make(self, name: str) -> Any:
        assert name == "broadcast"
        return self._manager


async def test_broadcast_channel_emits_a_broadcast_event() -> None:
    manager = BroadcastManager()
    notifications = NotificationManager(_FakeApp(manager))

    results = await notifications.send(User(7), OrderShipped(42))
    assert results["broadcast"] is True

    driver = manager.driver()
    assert isinstance(driver, LogBroadcaster)
    name, channels, event = driver.sent[0]
    assert name == "OrderShipped"
    assert channels == ["private-User.7"]
    assert isinstance(event, BroadcastNotification)


async def test_should_send_false_skips_that_channel_silently() -> None:
    class MailOnlyForVips(OrderShipped):
        def should_send(self, notifiable: Any, channel: str) -> bool:
            return channel != "broadcast"  # broadcast muted; mail/database still run

    results = await NotificationManager().send(User(1), MailOnlyForVips(1))
    assert "broadcast" not in results
    assert results["mail"] is True
    assert results["database"] == {"order_id": 1}
