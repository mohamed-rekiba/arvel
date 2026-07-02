"""A datetime-cast attribute must survive RAW-select hydration. The Builder's raw read path
(``select_raw``) returns column text on SQLite — ``'2026-07-02 21:41:10.506842'`` (space
separator, no offset) — and the "datetime" cast must interpret it as the stored UTC wall-clock,
exactly like the naive ``datetime`` the non-raw path yields."""

import datetime as _datetime

import pytest

from arvel.database.model import _from_db_datetime
from arvel.dates import Date


def test_sqlite_raw_string_is_parsed_as_utc() -> None:
    value = _from_db_datetime("2026-07-02 21:41:10.506842")
    assert isinstance(value, _datetime.datetime)
    assert value.tzinfo is not None
    assert value.utcoffset() == _datetime.timedelta(0)
    assert (value.year, value.hour, value.minute) == (2026, 21, 41)
    # and the cast's next step wraps it cleanly
    assert isinstance(Date.from_py(value), Date)


def test_aware_strings_and_datetimes_pass_through_correctly() -> None:
    aware = _from_db_datetime("2026-07-02T21:41:10+02:00")
    assert isinstance(aware, _datetime.datetime)
    assert aware.utcoffset() == _datetime.timedelta(hours=2)

    naive = _from_db_datetime(_datetime.datetime(2026, 7, 2, 21, 41, 10))
    assert naive.tzinfo is not None and naive.utcoffset() == _datetime.timedelta(0)

    already = _datetime.datetime(2026, 7, 2, tzinfo=_datetime.timezone.utc)
    assert _from_db_datetime(already) is already


def test_garbage_strings_still_raise() -> None:
    with pytest.raises(ValueError):
        Date.from_py(_from_db_datetime("not a datetime"))
