"""Dates (doc 14) — Date.parse format variants and diff_for_humans localization."""

from __future__ import annotations

import pytest

from arvel.dates import Date, DateParseError
from arvel.localization import current_locale


def test_parse_iso_unchanged() -> None:
    assert Date.parse("2024-01-01T00:00:00+00:00[UTC]").to_iso() == "2024-01-01T00:00:00+00:00[UTC]"


def test_parse_date_only() -> None:
    d = Date.parse("2024-01-02", tz="UTC")
    assert d.to_iso() == "2024-01-02T00:00:00+00:00[UTC]"


def test_parse_datetime_with_space_and_seconds() -> None:
    d = Date.parse("2024-01-02 03:04:05", tz="UTC")
    assert d.to_iso() == "2024-01-02T03:04:05+00:00[UTC]"


def test_parse_datetime_with_space_no_seconds() -> None:
    d = Date.parse("2024-01-02 03:04", tz="UTC")
    assert d.to_iso() == "2024-01-02T03:04:00+00:00[UTC]"


def test_parse_naive_assumes_app_timezone_by_default() -> None:
    # no tz given -> falls back to _app_timezone() (UTC outside an app context), matching
    # the existing from_py naive-datetime convention.
    d = Date.parse("2024-01-02")
    assert d.to_iso() == "2024-01-02T00:00:00+00:00[UTC]"


def test_parse_explicit_format() -> None:
    d = Date.parse("02/01/2024", tz="UTC", format="%d/%m/%Y")
    assert d.to_iso() == "2024-01-02T00:00:00+00:00[UTC]"


def test_parse_explicit_format_with_time() -> None:
    d = Date.parse("2024-01-02 03:04 PM", tz="UTC", format="%Y-%m-%d %I:%M %p")
    assert d.to_iso() == "2024-01-02T15:04:00+00:00[UTC]"


def test_parse_invalid_raises_typed_error() -> None:
    with pytest.raises(DateParseError):
        Date.parse("not-a-date")


def test_parse_invalid_against_explicit_format_raises_typed_error() -> None:
    with pytest.raises(DateParseError):
        Date.parse("2024-01-02", format="%d/%m/%Y")


def test_date_parse_error_is_a_value_error() -> None:
    assert issubclass(DateParseError, ValueError)


BASE = Date.parse("2026-06-15T12:00:00+00:00[UTC]")


def test_diff_for_humans_default_english_unchanged() -> None:
    assert BASE.add(hours=3).diff_for_humans(BASE) == "in 3 hours"
    assert BASE.subtract(days=2).diff_for_humans(BASE) == "2 days ago"
    assert BASE.diff_for_humans(BASE) == "just now"


def test_diff_for_humans_explicit_locale_french() -> None:
    assert BASE.add(hours=3).diff_for_humans(BASE, locale="fr") == "dans 3 heures"
    assert BASE.subtract(days=2).diff_for_humans(BASE, locale="fr") == "il y a 2 jours"


def test_diff_for_humans_explicit_locale_german() -> None:
    assert BASE.add(days=1).diff_for_humans(BASE, locale="de") == "in 1 Tag"


def test_diff_for_humans_falls_back_to_current_locale() -> None:
    current_locale.set("fr")
    try:
        assert BASE.add(hours=3).diff_for_humans(BASE) == "dans 3 heures"
    finally:
        current_locale.set("en")


def test_parse_instant_and_offset_iso() -> None:
    """Plain ISO-8601 instants — the format every JS client emits via toISOString() — parse:
    Z-suffixed, with milliseconds, and with a UTC offset. The result lands in tz (or the
    app timezone), preserving the absolute moment."""
    assert (
        Date.parse("2026-07-19T00:30:00Z", tz="UTC").to_iso()
        == "2026-07-19T00:30:00+00:00[UTC]"
    )
    assert (
        Date.parse("2026-07-19T00:30:00.250Z", tz="UTC").to_iso()
        == "2026-07-19T00:30:00.25+00:00[UTC]"
    )
    # +02:00 offset: same instant, expressed in UTC
    assert (
        Date.parse("2026-07-19T02:30:00+02:00", tz="UTC").to_iso()
        == "2026-07-19T00:30:00+00:00[UTC]"
    )
    # a T-separated naive datetime behaves like the space-separated one
    assert (
        Date.parse("2026-07-19T00:30:00", tz="UTC").to_iso()
        == "2026-07-19T00:30:00+00:00[UTC]"
    )
