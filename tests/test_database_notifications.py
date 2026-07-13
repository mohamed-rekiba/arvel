"""Database notifications (doc 16). The ``database`` channel persists a row in the
``notifications`` table; a ``Notifiable`` model retrieves them (``notifications`` / ``unread_notifications``)
and marks them read (``mark_as_read`` / ``mark_all_notifications_as_read``). Without a bound DB the channel
gracefully returns the payload array instead of persisting."""

from __future__ import annotations

from typing import Any, ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.kernel import Application, set_application
from arvel.notifications import DatabaseNotification, Notifiable, Notification, NotificationManager


class _User(Notifiable, Model):
    __table_name__ = "users"
    __fields__: ClassVar[dict[str, type]] = {"name": str}
    __fillable__: ClassVar[list[str]] = ["name"]


class _Welcome(Notification):
    def via(self, notifiable: Any) -> list[str]:
        return ["database"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"msg": "hi"}


async def _setup() -> tuple[Application, ConnectionResolver]:
    app = Application()
    db = ConnectionResolver()
    app.instance("db", db)
    set_application(app)
    for model in (_User, DatabaseNotification):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return app, db


async def test_database_channel_persists_a_row() -> None:
    _app, db = await _setup()
    try:
        user = await _User.create(name="Ada")
        await user.notify(_Welcome())
        rows = await user.notifications()
        assert len(rows) == 1
        assert rows[0].type == "_Welcome"
        assert rows[0].notifiable_type == "_User"
        assert rows[0].notifiable_id == str(user.id)
        assert rows[0].data == {"msg": "hi"}
        assert rows[0].unread is True and rows[0].read is False
    finally:
        set_application(None)
        await db.dispose()


async def test_mark_as_read_moves_it_out_of_unread() -> None:
    _app, db = await _setup()
    try:
        user = await _User.create(name="Ada")
        await user.notify(_Welcome())
        assert len(await user.unread_notifications()) == 1
        note = (await user.notifications())[0]
        await note.mark_as_read()
        assert note.read is True
        assert len(await user.unread_notifications()) == 0  # no longer unread
        assert len(await user.notifications()) == 1  # still present, just read
    finally:
        set_application(None)
        await db.dispose()


async def test_mark_all_as_read() -> None:
    _app, db = await _setup()
    try:
        user = await _User.create(name="Ada")
        await user.notify(_Welcome())
        await user.notify(_Welcome())
        assert len(await user.unread_notifications()) == 2
        await user.mark_all_notifications_as_read()
        assert len(await user.unread_notifications()) == 0
    finally:
        set_application(None)
        await db.dispose()


async def test_database_channel_without_db_returns_the_array() -> None:
    set_application(None)  # no app / no DB bound
    results = await NotificationManager().send_now(object(), _Welcome())
    assert results["database"] == {"msg": "hi"}  # graceful fallback, no persistence
