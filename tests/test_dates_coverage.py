"""Coverage — Date edge methods (doc 14)."""

from __future__ import annotations

from arvel.dates import Date

_ISO = "2024-01-01T00:00:00+00:00[UTC]"


def test_parse_passthrough_and_iso() -> None:
    existing = Date.now()
    assert Date.parse(existing) is existing  # a Date passes through
    assert isinstance(Date.parse(_ISO), Date)


def test_add_subtract() -> None:
    day = Date.parse(_ISO)
    assert day.add(days=1).to_iso().startswith("2024-01-02")
    assert day.subtract(days=1).to_iso().startswith("2023-12-31")


def test_eq_and_repr() -> None:
    a = Date.parse(_ISO)
    b = Date.parse(_ISO)
    assert a == b
    assert a != "not-a-date"
    assert repr(a).startswith("Date(")


def test_diff_for_humans_returns_phrase() -> None:
    assert isinstance(Date.now().diff_for_humans(), str)


def test_dst_spring_forward_calendar_vs_exact() -> None:
    """At spring-forward (America/New_York 2025-03-09 02:00->03:00, an hour vanishes), a
    *calendar* day keeps the wall-clock time while *exact* hours track real elapsed time."""
    from arvel.dates import Date

    start = Date.parse("2025-03-09T01:30:00-05:00[America/New_York]")
    assert start.add(days=1).to_iso() == "2025-03-10T01:30:00-04:00[America/New_York]"  # 01:30 kept
    assert (
        start.add(hours=24).to_iso() == "2025-03-10T02:30:00-04:00[America/New_York]"
    )  # +1h drift


def test_dst_fall_back_calendar_vs_exact() -> None:
    """At fall-back (2025-11-02 02:00->01:00, an hour repeats), +1 day keeps 01:30 while
    +24 exact hours lands an hour earlier on the wall clock."""
    from arvel.dates import Date

    start = Date.parse("2025-11-02T01:30:00-04:00[America/New_York]")
    assert start.add(days=1).to_iso() == "2025-11-03T01:30:00-05:00[America/New_York]"
    assert start.add(hours=24).to_iso() == "2025-11-03T00:30:00-05:00[America/New_York]"


def test_dates_order_naturally() -> None:
    """Carbon parity: Date instances compare by instant (`<`, `<=`, `>`, `>=`)."""
    from arvel.dates import Date

    earlier = Date.now().subtract(hours=1)
    later = Date.now()
    assert earlier < later and earlier <= later
    assert later > earlier and later >= earlier
    assert not (later < earlier)
    same = later
    assert same <= later and same >= later


def test_ordering_a_date_against_a_non_date_is_a_typeerror() -> None:
    """The ordering dunders return NotImplemented for foreign types, so Python raises its
    standard TypeError (not an AttributeError from poking other._dt)."""
    import pytest

    from arvel.dates import Date

    for expr in (
        lambda: Date.now() < 5,
        lambda: Date.now() <= "2026-01-01",
        lambda: Date.now() > object(),
        lambda: Date.now() >= None,
    ):
        with pytest.raises(TypeError):
            expr()
