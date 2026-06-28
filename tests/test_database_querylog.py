"""Advanced DB (doc 08) — query log + QueryExecuted event. Written test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import Builder, ConnectionResolver, QueryExecuted

_md = sa.MetaData()
widgets = sa.Table(
    "widgets", _md, sa.Column("id", sa.Integer, primary_key=True), sa.Column("name", sa.String)
)


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    await db.execute(sa.schema.CreateTable(widgets))
    return db


async def test_query_log_records_sql_and_timing() -> None:
    db = await _db()
    try:
        db.enable_query_log()
        await Builder(widgets, db).insert({"name": "a"})
        await Builder(widgets, db).where(name="a").get()
        log = db.get_query_log()
        assert len(log) >= 2
        assert "sql" in log[0]
        assert "time_ms" in log[0]
        assert isinstance(log[0]["time_ms"], float)
    finally:
        await db.dispose()


async def test_query_log_disabled_by_default_and_toggles() -> None:
    db = await _db()
    try:
        await Builder(widgets, db).get()
        assert db.get_query_log() == []  # disabled → nothing recorded
        db.enable_query_log()
        await Builder(widgets, db).get()
        assert len(db.get_query_log()) == 1
        db.flush_query_log()
        assert db.get_query_log() == []
        db.disable_query_log()
        await Builder(widgets, db).get()
        assert db.get_query_log() == []
    finally:
        await db.dispose()


async def test_query_executed_event_dispatched_when_events_bound() -> None:
    from arvel.events import Dispatcher
    from arvel.kernel import Application, set_application

    app = Application()
    dispatcher = Dispatcher()
    seen: list[str] = []
    dispatcher.listen(QueryExecuted, lambda event: seen.append(event.sql))
    app.instance("events", dispatcher)
    set_application(app)
    db = ConnectionResolver()
    try:
        await db.execute(sa.schema.CreateTable(widgets))
        await Builder(widgets, db).get()
        assert seen, "QueryExecuted should have been dispatched"
        assert "widgets" in seen[-1]
    finally:
        set_application(None)
        await db.dispose()
