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
