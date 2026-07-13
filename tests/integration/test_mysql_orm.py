"""The ORM compiles + round-trips against a real MySQL, including DateTime columns on MySQL's
`DATETIME`/`TIMESTAMP` types.
"""

from __future__ import annotations

import datetime as dt
from typing import ClassVar

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.dates import Date

pytestmark = pytest.mark.integration


class MysqlSku(Model):
    __table_name__ = "mysql_skus"
    __fields__: ClassVar = {"sku": str, "price": int}
    __fillable__: ClassVar = ["sku", "price"]
    __timestamps__ = False


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
        # datetimes round-trip and read back as Date, not strings
        assert isinstance(found.created_at, Date)
        assert isinstance(found.starts_at, Date)
        assert found.starts_at.to_iso().startswith("2026-06-29T09:00:00")

        many = await Gizmo.where("qty", ">", 5).get()
        assert [g.name for g in many] == ["sprocket"]
        assert await Gizmo.count() == 2

        # a Date passed straight to where() binds against the real DATETIME column
        early = await Gizmo.where(
            "starts_at", "<", Date.parse("2026-06-30T00:00:00+00:00[UTC]")
        ).get()
        assert [g.name for g in early] == ["widget"]
    finally:
        await db.execute(sa.schema.DropTable(Gizmo.__table__))
        await db.dispose()


async def test_upsert_uses_on_duplicate_key_update_on_mysql(mysql_url: str) -> None:
    """09 DB-QUERY A4 — MySQL/MariaDB upsert routes to ``ON DUPLICATE KEY UPDATE`` (not the
    Postgres/SQLite ``ON CONFLICT`` dialect, the A4 bug)."""
    db = ConnectionResolver({"default": {"url": mysql_url}})
    MysqlSku.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(MysqlSku.__table__))
        await db.statement("CREATE UNIQUE INDEX ux_mysql_skus_sku ON mysql_skus (sku)")

        await MysqlSku.upsert(
            [{"sku": "A", "price": 10}, {"sku": "B", "price": 20}], ["sku"], ["price"]
        )
        assert await MysqlSku.count() == 2

        # conflict on sku=A → UPDATE price in place, not a duplicate row
        await MysqlSku.upsert([{"sku": "A", "price": 99}], ["sku"], ["price"])
        assert await MysqlSku.count() == 2
        a = await MysqlSku.where(sku="A").first()
        assert a.price == 99
    finally:
        await db.execute(sa.schema.DropTable(MysqlSku.__table__))
        await db.dispose()
