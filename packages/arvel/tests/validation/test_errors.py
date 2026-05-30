"""Validation error objects."""

from __future__ import annotations

from arvel.validation.errors import ValidationRuleError


def test_validation_rule_error_carries_context() -> None:
    error = ValidationRuleError(field="email", rule="required", message="invalid")

    assert error.field == "email"
    assert error.message == "invalid"
    assert error.rule == "required"
    assert str(error) == "invalid"
