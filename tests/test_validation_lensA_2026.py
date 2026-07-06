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
    # build the non-ASCII digits by codepoint so no ambiguous glyphs sit in the source
    arabic_555 = chr(0x0665) * 3  # Arabic-Indic five
    superscript_2 = chr(0x00B2)  # also crashes a downstream int()
    persian_12 = chr(0x06F1) + chr(0x06F2)  # Extended Arabic-Indic one, two
    assert _passes({"x": "555"}, {"x": "digits:3"})
    assert not _passes({"x": arabic_555}, {"x": "digits:3"})
    assert not _passes({"x": superscript_2}, {"x": "integer"})
    assert not _passes({"x": persian_12}, {"x": "digits_between:1,3"})


def test_nullable_does_not_suppress_implicit_rules() -> None:
    # nullable suppresses type rules on None but required-family still runs and fails
    assert _passes({"x": None}, {"x": "nullable|integer"})
    assert not _passes({"x": None}, {"x": "required|nullable"})
    assert not _passes({"x": None, "y": "hi"}, {"x": "nullable|required_with:y"})
