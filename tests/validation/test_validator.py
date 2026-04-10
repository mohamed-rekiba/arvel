"""Tests for the Validator engine and Rule protocol.

Covers Story 1 (Form Request / Validator) and Story 3 (Custom Rules).
Tests must compile but FAIL until implementation exists.
"""

from __future__ import annotations

from typing import Any

import pytest

from arvel.validation.exceptions import FieldError, ValidationError
from arvel.validation.rule import Rule

# ──── Rule Protocol Conformance ────


class AlwaysPassRule:
    def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
        return True

    def message(self) -> str:
        return "This rule always passes."


class AlwaysFailRule:
    def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
        return False

    def message(self) -> str:
        return "This rule always fails."


class MinLengthRule:
    def __init__(self, min_length: int) -> None:
        self._min_length = min_length

    def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
        return isinstance(value, str) and len(value) >= self._min_length

    def message(self) -> str:
        return f"Must be at least {self._min_length} characters."


class PasswordStrengthRule:
    def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
        if not isinstance(value, str):
            return False
        has_upper = any(c.isupper() for c in value)
        has_lower = any(c.islower() for c in value)
        has_digit = any(c.isdigit() for c in value)
        return len(value) >= 8 and has_upper and has_lower and has_digit

    def message(self) -> str:
        return "Password must be 8+ chars with upper, lower, and digit."


def test_rule_protocol_conformance_passes():
    rule = AlwaysPassRule()
    assert isinstance(rule, Rule)


def test_rule_protocol_conformance_fails_without_methods():
    class NotARule:
        pass

    assert not isinstance(NotARule(), Rule)


# ──── Validator Engine ────


async def test_validate_with_no_rules_succeeds():
    from arvel.validation.validator import Validator

    validator = Validator()
    result = await validator.validate({"name": "Alice"}, {})
    assert result == {"name": "Alice"}


async def test_validate_with_passing_rule_succeeds():
    from arvel.validation.validator import Validator

    validator = Validator()
    result = await validator.validate(
        {"name": "Alice"},
        {"name": [AlwaysPassRule()]},
    )
    assert result == {"name": "Alice"}


async def test_validate_with_failing_rule_raises():
    from arvel.validation.validator import Validator

    validator = Validator()
    with pytest.raises(ValidationError) as exc_info:
        await validator.validate(
            {"name": "Alice"},
            {"name": [AlwaysFailRule()]},
        )
    errors = exc_info.value.errors
    assert len(errors) == 1
    assert errors[0].field == "name"
    assert errors[0].rule == "AlwaysFailRule"


async def test_validate_collects_all_field_errors():
    from arvel.validation.validator import Validator

    validator = Validator()
    with pytest.raises(ValidationError) as exc_info:
        await validator.validate(
            {"name": ""},
            {"name": [AlwaysFailRule(), MinLengthRule(3)]},
        )
    errors = exc_info.value.errors
    assert len(errors) == 2
    fields = {e.field for e in errors}
    assert fields == {"name"}


async def test_validate_multiple_fields_collects_errors():
    from arvel.validation.validator import Validator

    validator = Validator()
    with pytest.raises(ValidationError) as exc_info:
        await validator.validate(
            {"name": "", "email": ""},
            {
                "name": [AlwaysFailRule()],
                "email": [AlwaysFailRule()],
            },
        )
    errors = exc_info.value.errors
    fields = {e.field for e in errors}
    assert fields == {"name", "email"}


async def test_validate_with_parameterized_rule():
    from arvel.validation.validator import Validator

    validator = Validator()
    result = await validator.validate(
        {"name": "Alice"},
        {"name": [MinLengthRule(3)]},
    )
    assert result == {"name": "Alice"}


async def test_validate_parameterized_rule_fails():
    from arvel.validation.validator import Validator

    validator = Validator()
    with pytest.raises(ValidationError) as exc_info:
        await validator.validate(
            {"name": "Al"},
            {"name": [MinLengthRule(3)]},
        )
    assert exc_info.value.errors[0].message == "Must be at least 3 characters."


async def test_validate_password_strength_passes():
    from arvel.validation.validator import Validator

    validator = Validator()
    result = await validator.validate(
        {"password": "Secret1x"},
        {"password": [PasswordStrengthRule()]},
    )
    assert result == {"password": "Secret1x"}


async def test_validate_password_strength_fails():
    from arvel.validation.validator import Validator

    validator = Validator()
    with pytest.raises(ValidationError):
        await validator.validate(
            {"password": "weak"},
            {"password": [PasswordStrengthRule()]},
        )


# ──── Async Rules ────


class AsyncAlwaysPassRule:
    async def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
        return True

    def message(self) -> str:
        return "Async pass."


class AsyncAlwaysFailRule:
    async def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
        return False

    def message(self) -> str:
        return "Async fail."


async def test_validate_with_async_rule_passes():
    from arvel.validation.validator import Validator

    validator = Validator()
    result = await validator.validate(
        {"name": "Alice"},
        {"name": [AsyncAlwaysPassRule()]},
    )
    assert result == {"name": "Alice"}


async def test_validate_with_async_rule_fails():
    from arvel.validation.validator import Validator

    validator = Validator()
    with pytest.raises(ValidationError):
        await validator.validate(
            {"name": "Alice"},
            {"name": [AsyncAlwaysFailRule()]},
        )


async def test_validate_mixed_sync_and_async_rules():
    from arvel.validation.validator import Validator

    validator = Validator()
    with pytest.raises(ValidationError) as exc_info:
        await validator.validate(
            {"name": "Al"},
            {"name": [MinLengthRule(3), AsyncAlwaysFailRule()]},
        )
    assert len(exc_info.value.errors) == 2


# ──── Custom Messages ────


async def test_validate_with_custom_messages():
    from arvel.validation.validator import Validator

    validator = Validator()
    custom_messages = {"name.AlwaysFailRule": "Name is required, friend."}
    with pytest.raises(ValidationError) as exc_info:
        await validator.validate(
            {"name": ""},
            {"name": [AlwaysFailRule()]},
            messages=custom_messages,
        )
    assert exc_info.value.errors[0].message == "Name is required, friend."


# ──── FieldError / ValidationError Serialization ────


def test_field_error_to_dict():
    err = FieldError(field="email", rule="unique", message="Already taken.")
    assert err.to_dict() == {"field": "email", "rule": "unique", "message": "Already taken."}


def test_validation_error_to_dict():
    errors = [
        FieldError(field="name", rule="required", message="Name is required."),
        FieldError(field="email", rule="unique", message="Already taken."),
    ]
    exc = ValidationError(errors)
    d = exc.to_dict()
    assert d["message"] == "The given data was invalid."
    assert len(d["errors"]) == 2


def test_validation_error_custom_message():
    errors = [FieldError(field="x", rule="y", message="z")]
    exc = ValidationError(errors, message="Custom top-level.")
    assert exc.to_dict()["message"] == "Custom top-level."


def test_authorization_failed_error_default_message():
    from arvel.validation.exceptions import AuthorizationFailedError

    exc = AuthorizationFailedError()
    assert "unauthorized" in str(exc).lower()
    assert exc.detail == "This action is unauthorized."


def test_authorization_failed_error_custom_message():
    from arvel.validation.exceptions import AuthorizationFailedError

    exc = AuthorizationFailedError("Admin only.")
    assert str(exc) == "Admin only."
    assert exc.detail == "Admin only."
