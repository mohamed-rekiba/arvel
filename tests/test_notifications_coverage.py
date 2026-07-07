"""Coverage — Notification base defaults + apprise channel dispatch (doc 16)."""

from __future__ import annotations

from typing import Any

import apprise

from arvel.notifications import Notification, NotificationManager


def test_notification_base_defaults() -> None:
    note = Notification()
    assert note.via(object()) == ["mail"]
    assert note.to_array(object()) == {}
    assert note.apprise_urls(object()) == []


def test_apprise_client_is_real() -> None:
    assert isinstance(NotificationManager().apprise(), apprise.Apprise)


async def test_apprise_channel_dispatch() -> None:
    class Ping(Notification):
        def via(self, notifiable: Any) -> list[str]:
            return ["slack", "database"]

        def to_array(self, notifiable: Any) -> dict[str, Any]:
            return {"msg": "hi"}

    results = await NotificationManager().send("user", Ping())
    assert set(results) == {"slack", "database"}
    assert results["database"] == {"msg": "hi"}
    # the apprise channel ran (no servers configured → falsey result, but no error)
    assert results["slack"] in (False, None)


def test_to_apprise_default_derives_title_and_body() -> None:
    from arvel.notifications import AppriseMessage

    class Welcome(Notification):
        def to_array(self, notifiable: Any) -> dict[str, Any]:
            return {"subject": "Welcome", "body": "Thanks for joining"}

    message = Welcome().to_apprise(object())
    assert isinstance(message, AppriseMessage)
    assert message.title == "Welcome"
    assert message.body == "Thanks for joining"


def test_to_apprise_renders_key_value_lines_when_no_body_key() -> None:
    class Shipped(Notification):
        def to_array(self, notifiable: Any) -> dict[str, Any]:
            return {"order_id": 42, "status": "shipped"}

    message = Shipped().to_apprise(object())
    assert message.title == "Shipped"  # class-name fallback
    assert message.body == "order_id: 42\nstatus: shipped"  # readable lines, not str(dict)


async def test_apprise_driver_sends_structured_title_and_body() -> None:
    from arvel.notifications import AppriseMessage

    calls: list[dict[str, Any]] = []

    class RecordingClient:
        def add(self, url: str) -> None: ...

        async def async_notify(self, **kwargs: Any) -> bool:
            calls.append(kwargs)
            return True

    class Manager(NotificationManager):
        def apprise(self) -> Any:
            return RecordingClient()

    class Ship(Notification):
        def via(self, notifiable: Any) -> list[str]:
            return ["slack"]

        def apprise_urls(self, notifiable: Any) -> list[str]:
            return ["json://localhost"]

        def to_apprise(self, notifiable: Any) -> AppriseMessage:
            return AppriseMessage(body="Order shipped", title="Shipped", notify_type="success")

    results = await Manager().send("user", Ship())
    assert results["slack"] is True
    assert calls == [{"body": "Order shipped", "title": "Shipped", "notify_type": "success"}]
