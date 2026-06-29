"""Datetimes are stored as real (timezone-aware) DateTime values, not ISO strings (DR-0023).

Model timestamp/soft-delete/datetime-cast columns map to real ``sa.DateTime(timezone=True)`` (so they
round-trip on Postgres timestamptz, not just SQLite), are stamped/stored as stdlib datetimes, and read
back as arvel ``Date``. Covers the ``Date.from_py`` constructor too.
"""

from __future__ import annotations

import datetime as dt
from typing import ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model, SoftDeletes
from arvel.dates import Date

# --- Date.from_py -------------------------------------------------------------------


def test_from_py_aware_datetime() -> None:
    aware = dt.datetime(2026, 6, 29, 12, 0, tzinfo=dt.UTC)
    d = Date.from_py(aware, tz="UTC")
    assert isinstance(d, Date)
    assert d.to_iso().startswith("2026-06-29T12:00:00")


def test_from_py_naive_assumes_tz() -> None:
    naive = dt.datetime(2026, 6, 29, 12, 0)
    assert Date.from_py(naive, tz="UTC").to_iso().startswith("2026-06-29T12:00:00")


def test_from_py_passthrough_and_string_fallback() -> None:
    d = Date.now()
    assert Date.from_py(d) is d  # a Date passes through
    # a stored ISO string (e.g. from SQLite) still reads back as a Date
    iso = "2026-06-29T12:00:00+00:00[UTC]"
    assert Date.from_py(iso).to_iso().startswith("2026-06-29T12:00:00")


# --- column types -------------------------------------------------------------------


class Appt(Model):
    __fields__: ClassVar = {"name": str, "starts_at": dt.datetime}
    __fillable__: ClassVar = ["name", "starts_at"]
    __timestamps__ = True


class Token(Model):
    # a "datetime"-cast field declared as ``str`` must still get a real DateTime column
    __fields__: ClassVar = {"value": str, "expires_at": str}
    __casts__: ClassVar = {"expires_at": "datetime"}
    __fillable__: ClassVar = ["value", "expires_at"]


class Doc(Model, SoftDeletes):
    __fields__: ClassVar = {"title": str}
    __fillable__: ClassVar = ["title"]
    __timestamps__ = True


def _is_datetime_col(model: type[Model], col: str) -> bool:
    return isinstance(model.__table__.c[col].type, sa.DateTime)


def test_timestamp_and_field_columns_are_real_datetime() -> None:
    assert _is_datetime_col(Appt, "starts_at")  # datetime field
    assert _is_datetime_col(Appt, "created_at") and _is_datetime_col(Appt, "updated_at")
    assert _is_datetime_col(Token, "expires_at")  # str-declared but datetime-cast → DateTime
    assert _is_datetime_col(Doc, "deleted_at")  # soft-delete column


# --- round-trip on SQLite (real DateTime affinity) ----------------------------------


async def test_timestamps_round_trip_as_date() -> None:
    db = ConnectionResolver()
    Appt.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Appt.__table__))
        a = await Appt.create(name="x", starts_at=Date.parse("2026-06-29T09:00:00+00:00[UTC]"))
        found = await Appt.find(a.id)
        assert found is not None
        # timestamps read back as Date (Laravel parity), not str
        assert isinstance(found.created_at, Date)
        assert isinstance(found.updated_at, Date)
        # a datetime-cast field stores a real datetime and reads back as Date
        assert isinstance(found._attributes["starts_at"], dt.datetime)
        assert isinstance(found.starts_at, Date)
        assert found.starts_at.to_iso().startswith("2026-06-29T09:00:00")
    finally:
        await db.dispose()


async def test_round_trip_preserves_instant_under_non_utc_app_tz() -> None:
    """Regression (review B1): SQLite drops the tz offset and reads back a naive value. Datetimes are
    stored as UTC and read back as UTC, so a value stored under a non-UTC app timezone keeps its
    instant rather than being silently shifted."""
    from arvel.kernel import Application, set_application

    app = Application()
    app.make("config").set("app.timezone", "America/New_York")
    set_application(app)
    db = ConnectionResolver()
    Appt.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Appt.__table__))
        stored = Date.parse("2026-06-29T09:00:00+00:00[UTC]")
        a = await Appt.create(name="x", starts_at=stored)
        found = await Appt.find(a.id)
        assert found is not None
        assert found.starts_at == stored  # same instant (Date.__eq__ is instant-based), not shifted
    finally:
        await db.dispose()
        set_application(None)


async def test_where_accepts_a_date_directly() -> None:
    """N1: a Date can be passed to where() without dropping to .to_py() (Laravel accepts a Carbon)."""
    db = ConnectionResolver()
    Appt.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Appt.__table__))
        await Appt.create(name="early", starts_at=Date.parse("2026-06-01T00:00:00+00:00[UTC]"))
        await Appt.create(name="late", starts_at=Date.parse("2026-07-01T00:00:00+00:00[UTC]"))
        rows = await Appt.where(
            "starts_at", "<", Date.parse("2026-06-15T00:00:00+00:00[UTC]")
        ).get()
        assert [r.name for r in rows] == ["early"]
    finally:
        await db.dispose()


async def test_datetime_cast_accepts_iso_string_input() -> None:
    db = ConnectionResolver()
    Token.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Token.__table__))
        t = await Token.create(value="abc", expires_at="2026-12-31T23:59:00+00:00[UTC]")
        assert isinstance(t._attributes["expires_at"], dt.datetime)  # normalized to datetime
        found = await Token.find(t.id)
        assert found is not None and isinstance(found.expires_at, Date)
    finally:
        await db.dispose()


async def test_soft_delete_stamps_datetime() -> None:
    db = ConnectionResolver()
    Doc.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Doc.__table__))
        d = await Doc.create(title="t")
        await d.delete()  # soft delete → stamps deleted_at
        trashed = await Doc.with_trashed().where("id", "=", d.id).first()
        assert trashed is not None and isinstance(trashed.deleted_at, Date)
    finally:
        await db.dispose()
