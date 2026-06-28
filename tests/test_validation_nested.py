"""Validation (doc 10) — nested array rules (items.*.field)."""

from __future__ import annotations

from arvel.validation import Validator


def test_each_array_element_is_validated() -> None:
    data = {"items": [{"price": 10}, {"price": "bad"}, {"price": 5}]}
    validator = Validator(data, {"items.*.price": "required|numeric"})
    assert validator.fails()
    assert "items.1.price" in validator.errors()  # only the bad element
    assert "items.0.price" not in validator.errors()


def test_all_elements_valid_passes() -> None:
    data = {"items": [{"price": 10}, {"price": 20}]}
    assert Validator(data, {"items.*.price": "required|numeric"}).passes()


def test_missing_nested_value_fails_required() -> None:
    data = {"items": [{"price": 10}, {}]}
    validator = Validator(data, {"items.*.price": "required|numeric"})
    assert validator.fails()
    assert "items.1.price" in validator.errors()
