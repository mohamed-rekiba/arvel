"""Notifications (doc 16/12) — a ShouldQueue notification is enqueued, not fanned out inline."""

from __future__ import annotations

from typing import Any

from arvel.events import ShouldQueue
from arvel.kernel import Application, set_application
from arvel.notifications import Notification, NotificationManager, SendQueuedNotification


class Ping(Notification):
    def via(self, notifiable: Any) -> list[str]:
        return ["database"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"msg": "ping"}


class QueuedPing(Ping, ShouldQueue):
    pass


class FakeQueue:
    def __init__(self) -> None:
        self.pushed: list[Any] = []

    async def push_instance(self, job: Any) -> None:
        self.pushed.append(job)


async def test_should_queue_notification_is_enqueued() -> None:
    app = Application()
    mgr = NotificationManager(app)
    app.instance("notifications", mgr)
    fake = FakeQueue()
    app.instance("queue", fake)
    set_application(app)
    try:
        result = await mgr.send(object(), QueuedPing())
        assert result == {"queued": True}
        assert len(fake.pushed) == 1
        assert isinstance(fake.pushed[0], SendQueuedNotification)
    finally:
        set_application(None)


async def test_plain_notification_sends_inline() -> None:
    app = Application()
    mgr = NotificationManager(app)
    app.instance("notifications", mgr)
    app.instance("queue", FakeQueue())
    set_application(app)
    try:
        result = await mgr.send(object(), Ping())  # not ShouldQueue
        assert result == {"database": {"msg": "ping"}}
    finally:
        set_application(None)


async def test_queued_job_handle_fans_out() -> None:
    app = Application()
    mgr = NotificationManager(app)
    app.instance("notifications", mgr)
    set_application(app)
    try:
        result = await SendQueuedNotification(object(), QueuedPing()).handle()
        assert result == {"database": {"msg": "ping"}}
    finally:
        set_application(None)
