"""Full model event lifecycle (spec 08 §2 — Laravel eloquent events parity): every
``HasEvents.OBSERVABLE_EVENTS`` fires at the right point, in the right order, and
``creating``/``updating``/``saving``/``deleting``/``restoring`` cancel the operation when an
observer returns ``False`` (row unchanged, reload-verified)."""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model, SoftDeletes
from arvel.events import Dispatcher
from arvel.kernel import Application, set_application


class Widget(Model):
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]


class Trashable(Model, SoftDeletes):
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]


def _app_with_events(db: ConnectionResolver, *models: type[Model]) -> Application:
    app = Application()
    app.instance("events", Dispatcher())
    app.instance("db", db)
    set_application(app)
    for model in models:
        model.set_connection(db)
    return app


class Recorder:
    """An observer wiring every lifecycle hook it's given to a shared ``calls`` log."""

    def __init__(self, calls: list[str], *, veto: str | None = None) -> None:
        self._calls = calls
        self._veto = veto

    async def _record(self, hook: str) -> Any:
        self._calls.append(hook)
        return False if hook == self._veto else None

    async def retrieved(self, m: Any) -> Any:
        return await self._record("retrieved")

    async def creating(self, m: Any) -> Any:
        return await self._record("creating")

    async def created(self, m: Any) -> Any:
        return await self._record("created")

    async def updating(self, m: Any) -> Any:
        return await self._record("updating")

    async def updated(self, m: Any) -> Any:
        return await self._record("updated")

    async def saving(self, m: Any) -> Any:
        return await self._record("saving")

    async def saved(self, m: Any) -> Any:
        return await self._record("saved")

    async def deleting(self, m: Any) -> Any:
        return await self._record("deleting")

    async def deleted(self, m: Any) -> Any:
        return await self._record("deleted")

    async def trashed(self, m: Any) -> Any:
        return await self._record("trashed")

    async def restoring(self, m: Any) -> Any:
        return await self._record("restoring")

    async def restored(self, m: Any) -> Any:
        return await self._record("restored")

    async def force_deleting(self, m: Any) -> Any:
        return await self._record("force_deleting")

    async def force_deleted(self, m: Any) -> Any:
        return await self._record("force_deleted")

    async def replicating(self, m: Any) -> Any:
        return await self._record("replicating")


async def test_create_fires_saving_creating_created_saved_in_order() -> None:
    db = ConnectionResolver()
    _app_with_events(db, Widget)
    calls: list[str] = []
    try:
        await db.execute(sa.schema.CreateTable(Widget.__table__))
        Widget.observe(Recorder(calls))
        await Widget.create(name="a")
        assert calls == ["saving", "creating", "created", "saved"]
    finally:
        await db.dispose()
        set_application(None)


async def test_created_fires_once_on_create_not_on_update() -> None:
    db = ConnectionResolver()
    _app_with_events(db, Widget)
    calls: list[str] = []
    try:
        await db.execute(sa.schema.CreateTable(Widget.__table__))
        Widget.observe(Recorder(calls))
        widget = await Widget.create(name="a")
        assert calls.count("created") == 1

        widget.name = "b"
        await widget.save()
        assert calls.count("created") == 1  # unchanged — update doesn't re-fire it
        assert calls.count("updated") == 1
    finally:
        await db.dispose()
        set_application(None)


async def test_update_fires_saving_updating_updated_saved_in_order() -> None:
    db = ConnectionResolver()
    _app_with_events(db, Widget)
    try:
        await db.execute(sa.schema.CreateTable(Widget.__table__))
        widget = await Widget.create(name="a")
        calls: list[str] = []
        Widget.observe(Recorder(calls))
        widget.name = "b"
        await widget.save()
        assert calls == ["saving", "updating", "updated", "saved"]
    finally:
        await db.dispose()
        set_application(None)


async def test_creating_returning_false_cancels_create() -> None:
    db = ConnectionResolver()
    _app_with_events(db, Widget)
    calls: list[str] = []
    try:
        await db.execute(sa.schema.CreateTable(Widget.__table__))
        Widget.observe(Recorder(calls, veto="creating"))
        instance = Widget()
        instance.fill({"name": "blocked"})
        saved = await instance.save()
        assert saved is False
        assert await Widget.count() == 0  # no row written
        assert calls == ["saving", "creating"]  # never reached created/saved
    finally:
        await db.dispose()
        set_application(None)


async def test_updating_returning_false_cancels_update_row_unchanged() -> None:
    db = ConnectionResolver()
    _app_with_events(db, Widget)
    try:
        await db.execute(sa.schema.CreateTable(Widget.__table__))
        widget = await Widget.create(name="orig")
        calls: list[str] = []
        Widget.observe(Recorder(calls, veto="updating"))
        widget.name = "changed"
        saved = await widget.save()
        assert saved is False
        reloaded = await Widget.find(widget.id)
        assert reloaded is not None and reloaded.name == "orig"  # DB row untouched
    finally:
        await db.dispose()
        set_application(None)


async def test_deleting_returning_false_cancels_delete_row_survives() -> None:
    db = ConnectionResolver()
    _app_with_events(db, Widget)
    try:
        await db.execute(sa.schema.CreateTable(Widget.__table__))
        widget = await Widget.create(name="keep-me")
        calls: list[str] = []
        Widget.observe(Recorder(calls, veto="deleting"))
        deleted = await widget.delete()
        assert deleted is False
        assert calls == ["deleting"]
        assert await Widget.find(widget.id) is not None  # row survives (fires its own "retrieved")
    finally:
        await db.dispose()
        set_application(None)


async def test_soft_delete_fires_deleted_and_trashed_not_force_deleted() -> None:
    db = ConnectionResolver()
    _app_with_events(db, Trashable)
    calls: list[str] = []
    try:
        await db.execute(sa.schema.CreateTable(Trashable.__table__))
        row = await Trashable.create(name="soft")
        Trashable.observe(Recorder(calls))
        await row.delete()
        assert calls == ["deleting", "deleted", "trashed"]
        assert "force_deleting" not in calls and "force_deleted" not in calls
    finally:
        await db.dispose()
        set_application(None)


async def test_force_delete_fires_force_deleting_and_force_deleted_and_deleted() -> None:
    db = ConnectionResolver()
    _app_with_events(db, Trashable)
    calls: list[str] = []
    try:
        await db.execute(sa.schema.CreateTable(Trashable.__table__))
        row = await Trashable.create(name="hard")
        Trashable.observe(Recorder(calls))
        await row.force_delete()
        assert calls == ["force_deleting", "force_deleted", "deleted"]
    finally:
        await db.dispose()
        set_application(None)


async def test_restoring_returning_false_cancels_restore_stays_trashed() -> None:
    db = ConnectionResolver()
    _app_with_events(db, Trashable)
    try:
        await db.execute(sa.schema.CreateTable(Trashable.__table__))
        row = await Trashable.create(name="x")
        await row.delete()
        calls: list[str] = []
        Trashable.observe(Recorder(calls, veto="restoring"))
        restored = await row.restore()
        assert restored is False
        assert calls == ["restoring"]
        reloaded = await Trashable.with_trashed().where("id", "=", row.id).first()
        assert reloaded is not None and reloaded.trashed()  # still trashed
    finally:
        await db.dispose()
        set_application(None)


async def test_retrieved_fires_on_find_and_get() -> None:
    db = ConnectionResolver()
    _app_with_events(db, Widget)
    try:
        await db.execute(sa.schema.CreateTable(Widget.__table__))
        widget = await Widget.create(name="a")
        calls: list[str] = []
        Widget.observe(Recorder(calls))
        await Widget.find(widget.id)
        assert calls == ["retrieved"]

        calls.clear()
        await Widget.all()
        assert calls == ["retrieved"]
    finally:
        await db.dispose()
        set_application(None)


async def test_replicating_fires_best_effort_on_the_original() -> None:
    db = ConnectionResolver()
    _app_with_events(db, Widget)
    try:
        await db.execute(sa.schema.CreateTable(Widget.__table__))
        widget = await Widget.create(name="a")
        calls: list[str] = []
        Widget.observe(Recorder(calls))
        clone = widget.replicate()
        assert clone._exists is False
        # replicate() is sync (Laravel parity); the event dispatch it schedules is fire-and-forget
        # on the running loop — yield so the scheduled task actually runs before asserting.
        await asyncio.sleep(0.01)
        assert calls == ["replicating"]
    finally:
        await db.dispose()
        set_application(None)
