"""Integration (doc 20) — the ORM compiles + round-trips against a real MySQL (not just SQLite/PG).

Exercises the same surface as the Postgres test plus real DateTime columns (DR-0023), so the
cross-dialect SQLAlchemy Core construction is verified on MySQL's `DATETIME`/`TIMESTAMP` types too.
"""

from __future__ import annotations

import datetime as dt
from typing import ClassVar

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.dates import Date

pytestmark = pytest.mark.integration


class Gizmo(Model):
    __fields__: ClassVar = {"name": str, "qty": int, "starts_at": dt.datetime}
    __fillable__: ClassVar = ["name", "qty", "starts_at"]
    __timestamps__ = True


async def test_orm_and_datetime_round_trip_on_mysql(mysql_url: str) -> None:
    db = ConnectionResolver({"default": {"url": mysql_url}})
    Gizmo.set_connection(db)
    assert isinstance(Gizmo.__table__.c.starts_at.type, sa.DateTime)
    try:
        await db.execute(sa.schema.CreateTable(Gizmo.__table__))

        a = await Gizmo.create(
            name="widget", qty=3, starts_at=Date.parse("2026-06-29T09:00:00+00:00[UTC]")
        )
        await Gizmo.create(
            name="sprocket", qty=10, starts_at=Date.parse("2027-01-01T00:00:00+00:00[UTC]")
        )

        found = await Gizmo.find(a.id)
        assert found is not None and found.name == "widget"
        # real datetimes round-trip and read back as Date (Laravel parity), not strings
        assert isinstance(found.created_at, Date)
        assert isinstance(found.starts_at, Date)
        assert found.starts_at.to_iso().startswith("2026-06-29T09:00:00")

        many = await Gizmo.where("qty", ">", 5).get()
        assert [g.name for g in many] == ["sprocket"]
        assert await Gizmo.count() == 2

        # a Date passed straight to where() binds against the real DATETIME column (no .to_py())
        early = await Gizmo.where(
            "starts_at", "<", Date.parse("2026-06-30T00:00:00+00:00[UTC]")
        ).get()
        assert [g.name for g in early] == ["widget"]
    finally:
        await db.execute(sa.schema.DropTable(Gizmo.__table__))
        await db.dispose()
