"""Unit tests for constant_time_equals — must never raise on non-ASCII input."""

from __future__ import annotations

from arvel.support.secure_compare import constant_time_equals


def test_equal_ascii_strings() -> None:
    assert constant_time_equals("deadbeef", "deadbeef") is True


def test_unequal_ascii_strings() -> None:
    assert constant_time_equals("deadbeef", "cafebabe") is False


def test_non_ascii_input_returns_false_without_raising() -> None:
    # hmac.compare_digest raises TypeError on non-ASCII str; this must not.
    assert constant_time_equals("abc123", "café") is False


def test_both_non_ascii_unequal() -> None:
    assert constant_time_equals("naïve", "café") is False


def test_equal_non_ascii_strings() -> None:
    assert constant_time_equals("café", "café") is True


def test_length_mismatch_returns_false() -> None:
    assert constant_time_equals("short", "a-much-longer-value") is False
