"""Page-size clamping keeps a hostile ?limit/?offset from forcing huge scans."""

from __future__ import annotations

from app.http.controllers._deps import MAX_PAGE_LIMIT, clamp_limit, clamp_offset


def test_limit_is_capped_at_max() -> None:
    assert clamp_limit(10_000_000) == MAX_PAGE_LIMIT


def test_limit_floor_is_one() -> None:
    assert clamp_limit(0) == 1
    assert clamp_limit(-5) == 1


def test_limit_passes_through_within_bounds() -> None:
    assert clamp_limit(20) == 20
    assert clamp_limit(MAX_PAGE_LIMIT) == MAX_PAGE_LIMIT


def test_custom_maximum_is_honored() -> None:
    assert clamp_limit(500, maximum=5) == 5


def test_offset_floors_at_zero() -> None:
    assert clamp_offset(-1) == 0
    assert clamp_offset(0) == 0
    assert clamp_offset(42) == 42
