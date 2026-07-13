"""Regression: a model with ``__timestamps__`` used to store ISO strings, raising
``DatatypeMismatchError`` against real ``timestamp with time zone`` columns on Postgres."""

from __future__ import annotations

import datetime as dt
from typing import ClassVar

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.dates import Date

pytestmark = pytest.mark.integration


class Meeting(Model):
    __fields__: ClassVar = {"title": str, "starts_at": dt.datetime}
    __fillable__: ClassVar = ["title", "starts_at"]
    __timestamps__ = True


async def test_datetime_columns_round_trip_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    Meeting.set_connection(db)
    # timestamps + the datetime field compile to real timestamptz columns, not VARCHAR
    assert isinstance(Meeting.__table__.c.created_at.type, sa.DateTime)
    assert isinstance(Meeting.__table__.c.starts_at.type, sa.DateTime)
    try:
        await db.execute(sa.schema.CreateTable(Meeting.__table__))

        starts = Date.parse("2026-06-29T09:30:00+00:00[UTC]")
        m = await Meeting.create(title="standup", starts_at=starts)

        found = await Meeting.find(m.id)
        assert found is not None
        assert isinstance(found.created_at, Date)
        assert isinstance(found.starts_at, Date)
        assert found.starts_at.to_iso().startswith("2026-06-29T09:30:00")

        # a Date passed straight to where() binds against the real timestamptz column
        later = await Meeting.where(
            "starts_at", "<", Date.parse("2026-07-01T00:00:00+00:00[UTC]")
        ).get()
        assert [x.title for x in later] == ["standup"]
    finally:
        await db.execute(sa.schema.DropTable(Meeting.__table__))
        await db.dispose()
