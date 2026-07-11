"""Model observers: an observer's hook methods run when the model fires
the matching lifecycle event, and a ``saving`` that returns ``False`` cancels the save."""

from __future__ import annotations

from typing import Any, ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.events import Dispatcher
from arvel.kernel import Application, set_application


class Gadget(Model):
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]
    __timestamps__ = True


def _app_with_events(db: ConnectionResolver) -> Application:
    app = Application()
    app.instance("events", Dispatcher())
    app.instance("db", db)
    set_application(app)
    Gadget.set_connection(db)
    return app


async def test_observer_runs_on_save_and_delete() -> None:
    calls: list[tuple[str, str]] = []

    class GadgetObserver:
        async def saved(self, gadget: Any) -> None:
            calls.append(("saved", gadget.name))

        async def deleted(self, gadget: Any) -> None:
            calls.append(("deleted", gadget.name))

    db = ConnectionResolver()
    _app_with_events(db)
    try:
        await db.execute(sa.schema.CreateTable(Gadget.__table__))
        Gadget.observe(GadgetObserver())

        gadget = await Gadget.create(name="widget")
        assert ("saved", "widget") in calls

        await gadget.delete()
        assert ("deleted", "widget") in calls
    finally:
        await db.dispose()
        set_application(None)


async def test_saving_returning_false_cancels_the_save() -> None:
    class Veto:
        async def saving(self, gadget: Any) -> bool:
            return False  # cancel every save

    db = ConnectionResolver()
    _app_with_events(db)
    try:
        await db.execute(sa.schema.CreateTable(Gadget.__table__))
        Gadget.observe(Veto())
        await Gadget.create(name="blocked")
        assert await Gadget.count() == 0  # the save was cancelled — no row written
    finally:
        await db.dispose()
        set_application(None)


DECLARED_CALLS: list[tuple[str, str]] = []


class DeclaredObserver:
    async def saved(self, model: Any) -> None:
        DECLARED_CALLS.append(("saved", model.name))


class Gizmo(Model):
    """Declarative observers — no provider boot() / observe() call anywhere."""

    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]
    __timestamps__ = True
    __observers__: ClassVar = (DeclaredObserver,)


async def test_declared_observers_wire_on_first_event() -> None:
    DECLARED_CALLS.clear()
    db = ConnectionResolver()
    app = Application()
    app.instance("events", Dispatcher())
    app.instance("db", db)
    set_application(app)
    Gizmo.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Gizmo.__table__))
        await Gizmo.create(name="sprocket")  # first event boots __observers__
        assert ("saved", "sprocket") in DECLARED_CALLS
        await Gizmo.create(name="cog")  # not double-wired
        assert DECLARED_CALLS.count(("saved", "cog")) == 1
    finally:
        await db.dispose()
        set_application(None)
