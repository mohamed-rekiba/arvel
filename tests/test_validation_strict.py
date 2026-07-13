"""Validation (doc 10) — opt-in strict mode. By default an unrecognized rule name is a silent no-op
(lenient, -compatible for forward-compat); ``strict=True`` turns a typo'd rule (``requried``)
into a loud ``UnknownValidationRule`` instead of a silently-passing field — a programmer error, not a
user-input error, so it is NOT a ``ValidationException``."""

from __future__ import annotations

import pytest

from arvel.validation import UnknownValidationRule, ValidationException, Validator


def test_unknown_rule_is_not_a_validation_exception() -> None:
    # locks the semantic: a typo'd rule is a programmer error, not user input -> never renders as 422
    assert not issubclass(UnknownValidationRule, ValidationException)


def test_unknown_rule_is_a_silent_noop_by_default() -> None:
    # lenient default preserved: a typo passes rather than blowing up
    v = Validator({"name": "Ada"}, {"name": "requried"})  # typo of "required"
    assert v.passes()


def test_strict_mode_raises_on_unknown_rule() -> None:
    v = Validator({"name": "Ada"}, {"name": "requried"}, strict=True)
    with pytest.raises(UnknownValidationRule) as ei:
        v.passes()
    assert "requried" in str(ei.value)


def test_strict_mode_passes_known_rules() -> None:
    v = Validator(
        {"name": "Ada", "age": 20}, {"name": "required|string", "age": "integer"}, strict=True
    )
    assert v.passes()  # no false positive on real rules


def test_strict_mode_allows_async_db_rules_in_sync_pass() -> None:
    # unique/exists are validated asynchronously; in the synchronous pass they must NOT be flagged
    # as unknown (no DB bound -> they no-op rather than raising)
    v = Validator({"email": "ada@x.com"}, {"email": "required|unique:users"}, strict=True)
    assert v.passes()


def test_strict_mode_does_not_flag_nullable_or_sometimes() -> None:
    v = Validator(
        {"name": "Ada"}, {"name": "required", "nick": "sometimes|nullable|string"}, strict=True
    )
    assert v.passes()


def test_strict_mode_raises_on_a_typo_of_a_story_12_rule() -> None:
    # the rule-breadth expansion (validation/rules.py) is checked in strict mode too — a typo'd
    # NEW rule name (e.g. "timezon") must raise just like a typo'd original one.
    v = Validator({"tz": "Europe/Paris"}, {"tz": "timezon"}, strict=True)
    with pytest.raises(UnknownValidationRule) as ei:
        v.passes()
    assert "timezon" in str(ei.value)


def test_strict_mode_recognizes_all_story_12_rules() -> None:
    v = Validator(
        {"a": "x", "n": 5},
        {"a": "uppercase|ascii", "n": "multiple_of:5|min_digits:1"},
        strict=True,
    )
    v.passes()  # must not raise — every name here is a real rule
