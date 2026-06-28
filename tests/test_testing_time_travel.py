"""Testing (doc 20) — time-travel helpers freeze the clock deterministically + isolated."""

from __future__ import annotations

from arvel.dates import Date, now
from arvel.testing import freeze_time, travel_back, travel_to


def test_travel_to_freezes_now() -> None:
    target = Date.parse("2030-01-01T00:00:00+00:00[UTC]")
    travel_to(target)
    try:
        assert now().to_iso() == target.to_iso()
    finally:
        travel_back()


def test_travel_back_unfreezes() -> None:
    travel_to(Date.parse("2030-01-01T00:00:00+00:00[UTC]"))
    travel_back()
    assert Date.test_now() is None


def test_freeze_time_restores_prior_state() -> None:
    assert Date.test_now() is None
    target = Date.parse("2031-06-15T12:00:00+00:00[UTC]")
    with freeze_time(target):
        assert now().to_iso() == target.to_iso()
    assert Date.test_now() is None  # restored


def test_freeze_time_nests_and_restores_outer() -> None:
    outer = Date.parse("2030-01-01T00:00:00+00:00[UTC]")
    inner = Date.parse("2040-01-01T00:00:00+00:00[UTC]")
    with freeze_time(outer):
        with freeze_time(inner):
            assert now().to_iso() == inner.to_iso()
        assert now().to_iso() == outer.to_iso()  # inner restored the outer freeze, not None
    assert Date.test_now() is None
