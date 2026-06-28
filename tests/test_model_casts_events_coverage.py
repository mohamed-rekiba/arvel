"""Coverage — Model casts (datetime/bool/int/json), app-bound db, model events (doc 07/11)."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.dates import Date
from arvel.events import Dispatcher
from arvel.kernel import Application, set_application


async def test_casts_events_and_app_db_resolution() -> None:
    app = Application()
    db = ConnectionResolver()
    dispatcher = Dispatcher()
    fired: list[str] = []
    dispatcher.listen("Evented.saved", lambda *a: fired.append("saved"))
    app.instance("db", db)  # model resolves its connection from the container
    app.instance("events", dispatcher)
    set_application(app)

    class Evented(Model):
        __fields__ = {"when": str, "flag": bool, "num": int, "meta": dict}
        __fillable__ = ["when", "flag", "num", "meta"]
        __casts__ = {"when": "datetime", "flag": "bool", "num": "int", "meta": "json"}

    try:
        await db.execute(sa.schema.CreateTable(Evented.__table__))
        created = await Evented.create(
            when=Date.parse("2024-01-01T00:00:00+00:00[UTC]"),
            flag=True,
            num=5,
            meta={"a": 1},
        )
        assert "saved" in fired  # model event dispatched via the container's events
        assert isinstance(created._attributes["when"], str)  # datetime cast on set → ISO
        assert isinstance(created._attributes["meta"], str)  # json cast on set → string

        reloaded = await Evented.find(created.id)  # read path resolved via app('db')
        assert reloaded is not None
        assert isinstance(reloaded.when, Date)  # datetime cast on get
        assert reloaded.flag is True  # bool cast
        assert reloaded.num == 5  # int cast
        assert reloaded.meta == {"a": 1}  # json cast
    finally:
        set_application(None)
        await db.dispose()
