"""Edge branches in Str padding, *_last lookups, password, and to_dict."""

from __future__ import annotations

import pytest
from arvel.support.str import Str


def test_pad_right_returns_unchanged_when_long_enough() -> None:
    assert Str.pad_right("hello", 3) == "hello"


def test_pad_both_returns_unchanged_when_long_enough() -> None:
    assert Str.pad_both("hello", 3) == "hello"


def test_after_last_returns_subject_when_missing() -> None:
    assert Str.after_last("a.b.c", "/") == "a.b.c"


def test_before_last_returns_subject_when_missing() -> None:
    assert Str.before_last("a.b.c", "/") == "a.b.c"


def test_password_rejects_non_positive_length() -> None:
    with pytest.raises(ValueError, match="length must be positive"):
        Str.password(0)
