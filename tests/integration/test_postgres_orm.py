"""Integration (doc 20) — the ORM compiles + round-trips against a real PostgreSQL, not SQLite."""

from __future__ import annotations

from typing import ClassVar

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model

pytestmark = pytest.mark.integration


class Gadget(Model):
    __fields__: ClassVar = {"name": str, "qty": int}
    __fillable__: ClassVar = ["name", "qty"]
    __timestamps__ = True


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
