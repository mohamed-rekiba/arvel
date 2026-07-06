"""Behavioral-parity fixes from the 2026-07 Lens-A audit: boolean acceptable set,
dot-path cross-field references, ASCII-only digit rules, and nullable-vs-implicit rules."""

from __future__ import annotations

from arvel.validation import ValidationException, Validator


def _passes(data: dict, rules: dict) -> bool:
    try:
        Validator(data, rules).validate()
    except ValidationException:
        return False
    return True


def test_boolean_rejects_the_strings_true_and_false() -> None:
    assert _passes({"x": "1"}, {"x": "boolean"})
    assert _passes({"x": "0"}, {"x": "boolean"})
    assert not _passes({"x": "true"}, {"x": "boolean"})
    assert not _passes({"x": "false"}, {"x": "boolean"})


def test_same_and_different_resolve_dot_paths() -> None:
    # same: on a nested target must compare the real nested value
    assert _passes({"a": "x", "box": {"b": "x"}}, {"a": "same:box.b"})
    assert not _passes({"a": "x", "box": {"b": "y"}}, {"a": "same:box.b"})
    # different: on equal nested values must FAIL (was inverted — compared against None)
    assert not _passes({"a": "x", "box": {"b": "x"}}, {"a": "different:box.b"})
    assert _passes({"a": "x", "box": {"b": "y"}}, {"a": "different:box.b"})


def test_digit_rules_reject_non_ascii_digits() -> None:
    assert _passes({"x": "555"}, {"x": "digits:3"})
    assert not _passes({"x": "٥٥٥"}, {"x": "digits:3"})  # Arabic-Indic
    assert not _passes({"x": "²"}, {"x": "integer"})  # superscript — also crashed downstream int()
    assert not _passes({"x": "۱۲"}, {"x": "digits_between:1,3"})


def test_nullable_does_not_suppress_implicit_rules() -> None:
    # nullable suppresses type rules on None but required-family still runs and fails
    assert _passes({"x": None}, {"x": "nullable|integer"})
    assert not _passes({"x": None}, {"x": "required|nullable"})
    assert not _passes({"x": None, "y": "hi"}, {"x": "nullable|required_with:y"})
