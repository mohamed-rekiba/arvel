"""Validation (doc 10) — conditional 'sometimes' rule."""

from __future__ import annotations

from arvel.validation import Validator


def test_sometimes_skips_absent_field() -> None:
    assert Validator({}, {"nickname": "sometimes|string|min:3"}).passes()


def test_sometimes_validates_when_present() -> None:
    validator = Validator({"nickname": "ab"}, {"nickname": "sometimes|string|min:3"})
    assert validator.fails()
    assert "nickname" in validator.errors()


def test_sometimes_passes_when_present_and_valid() -> None:
    assert Validator({"nickname": "ada"}, {"nickname": "sometimes|string|min:3"}).passes()
