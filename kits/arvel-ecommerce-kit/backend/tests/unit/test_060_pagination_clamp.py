"""Page-size clamping keeps a hostile ?limit/?offset from forcing huge scans."""

from __future__ import annotations

from app.http.controllers._deps import clamp_limit, clamp_offset

# With no app booted, config("pagination.max_limit", 100) falls back to 100.
_DEFAULT_MAX = 100


def test_limit_is_capped_at_max() -> None:
    assert clamp_limit(10_000_000) == _DEFAULT_MAX


def test_limit_floor_is_one() -> None:
    assert clamp_limit(0) == 1
    assert clamp_limit(-5) == 1


def test_limit_passes_through_within_bounds() -> None:
    assert clamp_limit(20) == 20
    assert clamp_limit(_DEFAULT_MAX) == _DEFAULT_MAX


def test_custom_maximum_is_honored() -> None:
    assert clamp_limit(500, maximum=5) == 5


def test_offset_floors_at_zero() -> None:
    assert clamp_offset(-1) == 0
    assert clamp_offset(0) == 0
    assert clamp_offset(42) == 42
