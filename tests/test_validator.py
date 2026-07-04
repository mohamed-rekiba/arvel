"""Rule-based Validator (Laravel-style rules + custom messages)."""

from __future__ import annotations

import pytest

from arvel.validation import ValidationException, Validator


def test_required_and_email_pass() -> None:
    v = Validator(
        {"name": "ada", "email": "ada@example.com"}, {"name": "required", "email": "required|email"}
    )
    assert v.passes()
    assert v.validated() == {"name": "ada", "email": "ada@example.com"}


def test_required_fails_with_message() -> None:
    v = Validator({}, {"name": "required"})
    assert v.fails()
    assert v.errors()["name"] == ["The name field is required."]


def test_email_and_min_max() -> None:
    v = Validator(
        {"email": "nope", "age": 5, "bio": "x"},
        {"email": "email", "age": "integer|min:18", "bio": "string|min:3"},
    )
    assert v.fails()
    assert set(v.errors()) == {"email", "age", "bio"}


def test_nullable_skips_when_absent() -> None:
    v = Validator({}, {"age": "nullable|integer|min:18"})
    assert v.passes()


def test_in_and_confirmed() -> None:
    v = Validator(
        {"role": "admin", "password": "secret", "password_confirmation": "secret"},
        {"role": "in:admin,user", "password": "confirmed"},
    )
    assert v.passes()
    bad = Validator(
        {"role": "ghost", "password": "a", "password_confirmation": "b"},
        {"role": "in:admin,user", "password": "confirmed"},
    )
    assert bad.fails()
    assert set(bad.errors()) == {"role", "password"}


def test_custom_messages_override() -> None:
    v = Validator({}, {"email": "required"}, {"email.required": "We need your email!"})
    v.passes()
    assert v.errors()["email"] == ["We need your email!"]


def test_validate_raises_422_with_errors() -> None:
    v = Validator({}, {"name": "required"})
    with pytest.raises(ValidationException) as exc:
        v.validate()
    assert exc.value.status == 422
    assert "name" in exc.value.errors


def test_min_max_numeric_vs_length() -> None:
    # numeric compares value; string compares length
    assert Validator({"n": 20}, {"n": "numeric|min:18|max:65"}).passes()
    assert Validator({"s": "abcd"}, {"s": "string|max:3"}).fails()
