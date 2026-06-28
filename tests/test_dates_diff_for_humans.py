"""Dates (doc 14) — diff_for_humans full range: seconds→years, past/future, singular/plural."""

from __future__ import annotations

import pytest

from arvel.dates import Date

BASE = Date.parse("2026-06-15T12:00:00+00:00[UTC]")


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        ({"seconds": 5}, "in 5 seconds"),
        ({"seconds": 1}, "in 1 second"),
        ({"minutes": 1}, "in 1 minute"),
        ({"minutes": 30}, "in 30 minutes"),
        ({"hours": 1}, "in 1 hour"),
        ({"hours": 3}, "in 3 hours"),
        ({"days": 1}, "in 1 day"),
        ({"days": 2}, "in 2 days"),
        ({"days": 10}, "in 1 week"),
        ({"days": 45}, "in 1 month"),
        ({"days": 400}, "in 1 year"),
    ],
)
def test_future_units(delta: dict[str, int], expected: str) -> None:
    assert BASE.add(**delta).diff_for_humans(BASE) == expected


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        ({"seconds": 5}, "5 seconds ago"),
        ({"hours": 2}, "2 hours ago"),
        ({"days": 3}, "3 days ago"),
        ({"days": 60}, "2 months ago"),
        ({"days": 800}, "2 years ago"),
    ],
)
def test_past_units(delta: dict[str, int], expected: str) -> None:
    assert BASE.subtract(**delta).diff_for_humans(BASE) == expected


def test_just_now_within_a_second() -> None:
    assert BASE.diff_for_humans(BASE) == "just now"
