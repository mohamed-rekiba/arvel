"""Coverage-closing behavioral tests for `arvel.notifications`: the callable
`receives_broadcast_notifications_on` override, `broadcast_with`'s payload, the manager's
`default_driver`, an apprise channel with a real URL to add, the events-bound after-commit
path, `later()`'s durable delayed-dispatch rail, `_route`'s "callable but returns None" default
fallback, `_broadcaster()`'s no-app fallback, and the lazy module `__getattr__`'s error path."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.events import Dispatcher, ShouldQueue
from arvel.kernel import Application, set_application
from arvel.notifications import (
    BroadcastNotification,
    Notification,
    NotificationManager,
    NotificationSettings,
    SendQueuedNotification,
)


class Ping(Notification):
    def via(self, notifiable: Any) -> list[str]:
        return ["database"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"msg": "ping"}


class QueuedPing(Ping, ShouldQueue):
    pass


def test_broadcast_on_uses_a_callable_override_when_present() -> None:
    class Custom:
        def receives_broadcast_notifications_on(self) -> str:
            return "custom-channel"

    event = BroadcastNotification(Custom(), Ping())
    assert event.broadcast_on() == ["custom-channel"]


def test_broadcast_with_defaults_to_to_broadcast() -> None:
    event = BroadcastNotification(object(), Ping())
    assert event.broadcast_with() == {"msg": "ping"}  # Ping has no to_broadcast override


def test_default_driver_reads_the_configured_channel() -> None:
    assert NotificationManager().default_driver() == NotificationSettings().default == "mail"


async def test_apprise_channel_adds_a_real_url() -> None:
    class UrlPing(Notification):
        def via(self, notifiable: Any) -> list[str]:
            return ["slack"]

        def apprise_urls(self, notifiable: Any) -> list[str]:
            return ["json://localhost/webhook"]

    results = await NotificationManager().send_now(object(), UrlPing())
    assert "slack" in results  # the URL was added and a (failed, but non-crashing) send attempted


class FakeQueue:
    def __init__(self) -> None:
        self.pushed: list[Any] = []
        self.delayed: list[tuple[float, Any]] = []

    async def push_instance(self, job: Any) -> None:
        self.pushed.append(job)

    async def dispatch_after(self, delay: float, job: Any) -> None:
        self.delayed.append((delay, job))


async def test_after_commit_routes_through_a_bound_events_dispatcher() -> None:
    app = Application()
    mgr = NotificationManager(app)
    app.instance("notifications", mgr)
    app.instance("events", Dispatcher(app))
    fake = FakeQueue()
    app.instance("queue", fake)
    set_application(app)
    try:
        result = await mgr.send(object(), QueuedPing())
        assert result == {"queued": True}
        assert len(fake.pushed) == 1  # ran immediately (no open transaction) via after_commit()
    finally:
        set_application(None)


async def test_later_queues_a_delayed_job_per_channel() -> None:
    app = Application()
    mgr = NotificationManager(app)
    app.instance("notifications", mgr)
    fake = FakeQueue()
    app.instance("queue", fake)
    set_application(app)
    try:
        result = await mgr.later(30.0, object(), Ping())
        assert result == {"queued": True}
        assert len(fake.delayed) == 1
        delay, job = fake.delayed[0]
        assert delay == 30.0
        assert isinstance(job, SendQueuedNotification)
    finally:
        set_application(None)


async def test_later_falls_back_to_send_now_without_a_bound_queue() -> None:
    mgr = NotificationManager()
    result = await mgr.later(30.0, object(), Ping())
    assert result == {"database": {"msg": "ping"}}


def test_route_falls_back_to_default_when_the_callable_returns_none() -> None:
    class PartiallyRouted:
        def route_notification_for(self, channel: str) -> Any:
            return None  # defines the hook, but has no route for this channel

    assert NotificationManager._route(PartiallyRouted(), "mail", "default@x.test") == (
        "default@x.test"
    )


async def test_broadcaster_falls_back_to_an_in_process_manager_without_a_bound_app() -> None:
    class BroadcastPing(Notification):
        def via(self, notifiable: Any) -> list[str]:
            return ["broadcast"]

    results = await NotificationManager().send_now(object(), BroadcastPing())
    assert results["broadcast"] is True  # BroadcastManager(None) still delivers (log driver)


def test_module_getattr_raises_for_an_unknown_name() -> None:
    import arvel.notifications as notifications_module

    with pytest.raises(AttributeError, match="not_a_real_export"):
        notifications_module.not_a_real_export
