"""Dates (doc 14/21) — locale-aware formatting via Babel, honoring current_locale."""

from __future__ import annotations

from arvel.dates import Date
from arvel.localization import current_locale


def _d() -> Date:
    return Date.parse("2026-06-23T14:30:00+00:00[UTC]")


def test_format_explicit_locale() -> None:
    assert _d().format_date("full", locale="fr") == "mardi 23 juin 2026"
    assert _d().format("short", locale="de") == "23.06.26, 14:30"


def test_format_defaults_to_current_locale() -> None:
    current_locale.set("fr")
    try:
        assert _d().format_date("full") == "mardi 23 juin 2026"
    finally:
        current_locale.set("en")


def test_format_time_only() -> None:
    out = _d().format_time("short", locale="en")
    assert "2:30" in out  # 12-hour clock in en
