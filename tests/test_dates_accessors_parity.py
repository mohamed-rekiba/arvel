"""Date accessor completeness (round H2)."""

from __future__ import annotations

import datetime as _dt

from arvel.dates import Date


def _at(iso: str) -> Date:
    return Date.from_py(_dt.datetime.fromisoformat(iso).replace(tzinfo=_dt.UTC), tz="UTC")


def test_start_of_month_week_year() -> None:
    d = _at("2026-07-08T13:45:00")  # a Wednesday
    assert d.start_of_month().to_iso().startswith("2026-07-01T00:00:00")
    assert d.start_of_year().to_iso().startswith("2026-01-01T00:00:00")
    assert d.start_of_week().to_iso().startswith("2026-07-06T00:00:00")  # Monday


def test_is_past_future_today() -> None:
    Date.set_test_now(_at("2026-07-06T12:00:00"))
    try:
        assert _at("2026-07-01T00:00:00").is_past()
        assert _at("2026-08-01T00:00:00").is_future()
        assert _at("2026-07-06T23:59:00").is_today()
        assert not _at("2026-07-05T23:59:00").is_today()
    finally:
        Date.set_test_now(None)


def test_diff_accessors_signed_and_truncated() -> None:
    a = _at("2026-01-01T00:00:00")
    b = _at("2026-01-10T06:00:00")
    assert a.diff_in_days(b) == 9  # 9.25 days truncated toward zero
    assert a.diff_in_hours(b) == 9 * 24 + 6
    assert b.diff_in_days(a) == -9  # signed
    assert a.diff_in_minutes(b) == (9 * 24 + 6) * 60
