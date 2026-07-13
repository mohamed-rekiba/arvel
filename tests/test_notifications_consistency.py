"""Entry 5.6 — notifications joins the house idioms: NotificationManager on the
``support.Manager`` base (driver registry + ``extend()``), a mass ``UPDATE`` for
``mark_all_notifications_as_read``, and soft-coupled ``NotificationSending``/``NotificationSent``
events (a listener returning ``False`` vetoes a channel)."""

from __future__ import annotations

from typing import Any, ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.events import Dispatcher
from arvel.kernel import Application, set_application
from arvel.notifications import (
    Notifiable,
    Notification,
    NotificationManager,
    NotificationSending,
    NotificationSent,
)
from arvel.support.manager import Manager


class _Welcome(Notification):
    def via(self, notifiable: Any) -> list[str]:
        return ["database"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"msg": "hi"}


class _User(Notifiable, Model):
    __table_name__ = "users"
    __fields__: ClassVar[dict[str, type]] = {"name": str}
    __fillable__: ClassVar[list[str]] = ["name"]


async def _setup() -> tuple[Application, ConnectionResolver]:
    app = Application()
    db = ConnectionResolver()
    app.instance("db", db)
    set_application(app)
    from arvel.notifications import DatabaseNotification

    for model in (_User, DatabaseNotification):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return app, db


def test_manager_is_a_support_manager_with_a_driver_registry() -> None:
    assert isinstance(NotificationManager(), Manager)
    mgr = NotificationManager()
    assert isinstance(mgr.driver("mail"), object)
    assert mgr.driver("database") is mgr.driver("database")  # cached, same instance


async def test_custom_channel_via_extend() -> None:
    class _Recorder:
        def __init__(self) -> None:
            self.sent: list[tuple[Any, Any]] = []

        async def send(self, channel: str, notifiable: Any, notification: Notification) -> Any:
            self.sent.append((notifiable, notification))
            return "sms-ok"

    recorder = _Recorder()
    mgr = NotificationManager()
    mgr.extend("sms", lambda _app: recorder)

    class _Sms(Notification):
        def via(self, notifiable: Any) -> list[str]:
            return ["sms"]

    result = await mgr.send_now("+1000", _Sms())
    assert result == {"sms": "sms-ok"}
    assert len(recorder.sent) == 1


async def test_unregistered_channel_still_falls_through_to_apprise() -> None:
    mgr = NotificationManager()

    class _Ping(Notification):
        def via(self, notifiable: Any) -> list[str]:
            return ["slack"]

    result = await mgr.send_now("user", _Ping())
    assert result["slack"] in (False, None)  # no servers configured, but no error


async def test_mark_all_as_read_is_one_mass_update() -> None:
    _app, db = await _setup()
    try:
        user = await _User.create(name="Ada")
        await user.notify(_Welcome())
        await user.notify(_Welcome())
        await user.notify(_Welcome())
        assert len(await user.unread_notifications()) == 3

        db.enable_query_log()
        await user.mark_all_notifications_as_read()
        queries = len(db.get_query_log())
        db.disable_query_log()

        assert queries == 1  # one UPDATE, not a per-row loop
        assert len(await user.unread_notifications()) == 0
    finally:
        set_application(None)
        await db.dispose()


async def test_notification_sending_veto_suppresses_that_channel() -> None:
    app = Application()
    events = Dispatcher()
    app.instance("events", events)
    mgr = NotificationManager(app)
    set_application(app)
    try:
        events.listen(NotificationSending, lambda e: False if e.channel == "database" else None)

        class _Multi(Notification):
            def via(self, notifiable: Any) -> list[str]:
                return ["database"]

            def to_array(self, notifiable: Any) -> dict[str, Any]:
                return {"x": 1}

        result = await mgr.send_now(object(), _Multi())
        assert result == {}  # vetoed → no result entry at all
    finally:
        set_application(None)


async def test_notification_sent_fires_after_a_successful_send() -> None:
    app = Application()
    events = Dispatcher()
    app.instance("events", events)
    mgr = NotificationManager(app)
    set_application(app)
    try:
        seen: list[NotificationSent] = []
        events.listen(NotificationSent, lambda e: seen.append(e))

        class _Multi(Notification):
            def via(self, notifiable: Any) -> list[str]:
                return ["database"]

            def to_array(self, notifiable: Any) -> dict[str, Any]:
                return {"x": 1}

        await mgr.send_now("user", _Multi())
        assert len(seen) == 1
        assert seen[0].channel == "database"
        assert seen[0].response == {"x": 1}
    finally:
        set_application(None)


async def test_no_events_bound_is_a_no_op() -> None:
    mgr = NotificationManager()  # no app at all

    class _Ping(Notification):
        def via(self, notifiable: Any) -> list[str]:
            return ["database"]

        def to_array(self, notifiable: Any) -> dict[str, Any]:
            return {"ok": True}

    result = await mgr.send_now("user", _Ping())
    assert result == {"database": {"ok": True}}
