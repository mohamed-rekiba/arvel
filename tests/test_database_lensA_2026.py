"""Behavioral-parity fixes from the 2026-07 Lens-A audit: mass-update stamps updated_at,
count() reflects distinct/joins, increment is atomic, exists() neither hydrates nor fires
the retrieved event."""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.events import Dispatcher
from arvel.kernel import Application, set_application


class Counter(Model):
    __fields__: ClassVar = {"name": str, "hits": int}
    __fillable__: ClassVar = ["name", "hits"]
    __timestamps__ = True


def _app(db: ConnectionResolver) -> Application:
    app = Application()
    app.instance("events", Dispatcher())
    app.instance("db", db)
    set_application(app)
    Counter.set_connection(db)
    return app


async def test_mass_update_stamps_updated_at() -> None:
    db = ConnectionResolver()
    _app(db)
    try:
        await db.execute(sa.schema.CreateTable(Counter.__table__))
        c = await Counter.create(name="a", hits=0)
        before = (await Counter.find(c.id)).updated_at
        await asyncio.sleep(0.01)
        await Counter.where("id", "=", c.id).update({"hits": 5})
        after = await Counter.find(c.id)
        assert after.hits == 5
        assert after.updated_at != before  # bulk update kept updated_at fresh
    finally:
        await db.dispose()
        set_application(None)


async def test_count_reflects_distinct() -> None:
    db = ConnectionResolver()
    _app(db)
    try:
        await db.execute(sa.schema.CreateTable(Counter.__table__))
        await Counter.create(name="x", hits=1)
        await Counter.create(name="x", hits=1)
        await Counter.create(name="y", hits=1)
        assert await Counter.query().count() == 3
        assert await Counter.query().select("name").distinct().count() == 2
    finally:
        await db.dispose()
        set_application(None)


async def test_increment_is_atomic_and_bumps_timestamp() -> None:
    db = ConnectionResolver()
    _app(db)
    try:
        await db.execute(sa.schema.CreateTable(Counter.__table__))
        c = await Counter.create(name="a", hits=10)
        before = (await Counter.find(c.id)).updated_at
        await asyncio.sleep(0.01)
        await c.increment("hits", 5)
        assert c.hits == 15
        after = await Counter.find(c.id)
        assert after.hits == 15
        assert after.updated_at != before
    finally:
        await db.dispose()
        set_application(None)


async def test_increment_fires_update_lifecycle_events() -> None:
    seen: list[str] = []

    class Watch:
        async def updating(self, m: Any) -> None:
            seen.append("updating")

        async def updated(self, m: Any) -> None:
            seen.append("updated")

        async def saved(self, m: Any) -> None:
            seen.append("saved")

    db = ConnectionResolver()
    _app(db)
    try:
        await db.execute(sa.schema.CreateTable(Counter.__table__))
        c = await Counter.create(name="a", hits=1)
        Counter.observe(Watch())
        await c.increment("hits")
        # atomic increment still runs the update lifecycle (observers must not silently stop)
        assert seen == ["updating", "updated", "saved"]
    finally:
        await db.dispose()
        set_application(None)


class NoTsCounter(Model):
    __fields__: ClassVar = {"name": str, "hits": int}
    __fillable__: ClassVar = ["name", "hits"]
    __timestamps__ = False


async def test_increment_on_model_without_timestamps() -> None:
    db = ConnectionResolver()
    app = Application()
    app.instance("events", Dispatcher())
    app.instance("db", db)
    set_application(app)
    NoTsCounter.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(NoTsCounter.__table__))
        c = await NoTsCounter.create(name="a", hits=1)
        await c.increment("hits", 4)  # no updated_at column to stamp
        assert c.hits == 5
        assert (await NoTsCounter.find(c.id)).hits == 5
    finally:
        await db.dispose()
        set_application(None)


class VetoCounter(Model):
    __fields__: ClassVar = {"name": str, "hits": int}
    __fillable__: ClassVar = ["name", "hits"]
    __timestamps__ = True


async def test_increment_cancelled_by_updating_observer() -> None:
    class Veto:
        async def updating(self, m: Any) -> bool:
            return False

    db = ConnectionResolver()
    app = Application()
    app.instance("events", Dispatcher())
    app.instance("db", db)
    set_application(app)
    VetoCounter.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(VetoCounter.__table__))
        c = await VetoCounter.create(name="a", hits=1)
        VetoCounter.observe(Veto())
        await c.increment("hits", 5)  # updating observer cancels → no write
        assert (await VetoCounter.find(c.id)).hits == 1
    finally:
        await db.dispose()
        set_application(None)


async def test_exists_does_not_fire_retrieved() -> None:
    seen: list[str] = []

    class Watch:
        async def retrieved(self, m: Any) -> None:
            seen.append(m.name)

    db = ConnectionResolver()
    _app(db)
    try:
        await db.execute(sa.schema.CreateTable(Counter.__table__))
        await Counter.create(name="a", hits=1)
        Counter.observe(Watch())
        assert await Counter.where("name", "=", "a").exists() is True
        assert await Counter.where("name", "=", "zzz").exists() is False
        assert seen == []  # a mere existence probe must not hydrate + fire retrieved
    finally:
        await db.dispose()
        set_application(None)
