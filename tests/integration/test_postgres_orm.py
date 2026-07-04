"""Integration (doc 20) — the ORM compiles + round-trips against a real PostgreSQL, not SQLite.

Also covers spec 08 (DB-MODEL): the new casts + the full model event lifecycle, against a real
Postgres connection (not just SQLite — Postgres has its own TEXT/DECIMAL column behavior)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.events import Dispatcher
from arvel.kernel import Application, set_application
from arvel.security import Encrypter
from arvel.support import Collection, Stringable

pytestmark = pytest.mark.integration


class Gadget(Model):
    __fields__: ClassVar = {"name": str, "qty": int}
    __fillable__: ClassVar = ["name", "qty"]
    __timestamps__ = True


class RichItem(Model):
    __fields__: ClassVar = {
        "tags": list,
        "extra": dict,
        "profile": dict,
        "price": str,
        "secret": str,
        "slug": str,
    }
    __fillable__: ClassVar = list(__fields__)
    __casts__: ClassVar = {
        "tags": "array",
        "extra": "collection",
        "profile": "object",
        "price": "decimal:2",
        "secret": "encrypted:array",
        "slug": "stringable",
    }


async def test_orm_roundtrip_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    Gadget.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Gadget.__table__))

        a = await Gadget.create(name="widget", qty=3)
        await Gadget.create(name="sprocket", qty=10)

        found = await Gadget.find(a.id)
        assert found is not None and found.name == "widget"

        many = await Gadget.where("qty", ">", 5).get()
        assert [g.name for g in many] == ["sprocket"]

        assert await Gadget.count() == 2
    finally:
        await db.execute(sa.schema.DropTable(Gadget.__table__))
        await db.dispose()


async def test_new_casts_round_trip_on_postgres(postgres_url: str) -> None:
    app = Application()
    app.instance("encrypter", Encrypter(Encrypter.generate_key()))
    set_application(app)
    db = ConnectionResolver({"default": {"url": postgres_url}})
    RichItem.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(RichItem.__table__))

        created = await RichItem.create(
            tags=["a", "b"],
            extra=Collection([1, 2]),
            profile={"name": "Ada"},
            price=Decimal("9.995"),
            secret=[1, "two", 3],
            slug="hello",
        )
        assert created.price == Decimal("10.00")  # quantized on set (bankers' rounding)

        reloaded = await RichItem.find(created.id)
        assert reloaded is not None
        assert reloaded.tags == ["a", "b"]
        assert isinstance(reloaded.extra, Collection) and reloaded.extra.all() == [1, 2]
        assert isinstance(reloaded.profile, SimpleNamespace) and reloaded.profile.name == "Ada"
        assert isinstance(reloaded.price, Decimal) and reloaded.price == Decimal("10.00")
        assert reloaded.secret == [1, "two", 3]
        assert isinstance(reloaded.slug, Stringable) and str(reloaded.slug) == "hello"

        # the encrypted column holds ciphertext at rest, not the plaintext JSON
        raw_row = await db.fetch_one(
            sa.select(RichItem.__table__.c.secret).where(RichItem.__table__.c.id == created.id)
        )
        assert raw_row is not None
        assert '"two"' not in raw_row["secret"]
    finally:
        await db.execute(sa.schema.DropTable(RichItem.__table__))
        await db.dispose()
        set_application(None)


async def test_full_event_lifecycle_on_postgres(postgres_url: str) -> None:
    app = Application()
    app.instance("events", Dispatcher())
    set_application(app)
    db = ConnectionResolver({"default": {"url": postgres_url}})
    Gadget.set_connection(db)
    calls: list[str] = []

    class Recorder:
        async def _log(self, hook: str) -> None:
            calls.append(hook)

        async def creating(self, m: Any) -> None:
            await self._log("creating")

        async def created(self, m: Any) -> None:
            await self._log("created")

        async def updating(self, m: Any) -> None:
            await self._log("updating")

        async def updated(self, m: Any) -> None:
            await self._log("updated")

        async def retrieved(self, m: Any) -> None:
            await self._log("retrieved")

        async def deleted(self, m: Any) -> None:
            await self._log("deleted")

    try:
        await db.execute(sa.schema.CreateTable(Gadget.__table__))
        Gadget.observe(Recorder())

        widget = await Gadget.create(name="widget", qty=1)
        assert calls == ["creating", "created"]

        calls.clear()
        widget.qty = 2
        await widget.save()
        assert calls == ["updating", "updated"]

        calls.clear()
        await Gadget.find(widget.id)
        assert calls == ["retrieved"]

        calls.clear()
        await widget.delete()
        assert calls == ["deleted"]
    finally:
        await db.execute(sa.schema.DropTable(Gadget.__table__))
        await db.dispose()
        set_application(None)
