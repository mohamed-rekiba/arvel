"""ch 10 — min/max compare a numeric-typed field by VALUE, not string length. Form input is
strings, so `integer|min:18` on "18" must pass (it was failing: len("18")=2 < 18)."""

from __future__ import annotations

from arvel.validation import Validator


def test_min_numeric_string_field_compares_by_value() -> None:
    assert Validator({"age": "18"}, {"age": "integer|min:18"}).passes()
    assert Validator({"age": "17"}, {"age": "integer|min:18"}).fails()


def test_max_numeric_string_field_compares_by_value() -> None:
    assert Validator({"qty": "5"}, {"qty": "numeric|max:10"}).passes()
    assert Validator({"qty": "11"}, {"qty": "numeric|max:10"}).fails()


def test_min_non_numeric_field_still_uses_length() -> None:
    assert Validator({"name": "ab"}, {"name": "string|min:3"}).fails()
    assert Validator({"name": "abcd"}, {"name": "string|min:3"}).passes()


def test_numeric_int_value_unaffected() -> None:
    assert Validator({"age": 21}, {"age": "integer|min:18"}).passes()
    assert Validator({"age": 16}, {"age": "integer|min:18"}).fails()
