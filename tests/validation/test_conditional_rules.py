"""Tests for conditional validation rules — Story 4.

Tests must compile but FAIL until implementation exists.
"""

from __future__ import annotations

from typing import Any

import pytest

from arvel.validation.exceptions import ValidationError

# ──── RequiredIf ────


async def test_required_if_field_required_when_condition_met():
    from arvel.validation.rules.conditional import RequiredIf
    from arvel.validation.validator import Validator

    validator = Validator()
    with pytest.raises(ValidationError) as exc_info:
        await validator.validate(
            {"role": "admin"},
            {"permissions": [RequiredIf("role", "admin")]},
        )
    assert any(e.field == "permissions" for e in exc_info.value.errors)


async def test_required_if_field_optional_when_condition_not_met():
    from arvel.validation.rules.conditional import RequiredIf
    from arvel.validation.validator import Validator

    validator = Validator()
    result = await validator.validate(
        {"role": "user"},
        {"permissions": [RequiredIf("role", "admin")]},
    )
    assert "permissions" not in result or result.get("permissions") is None


# ──── RequiredUnless ────


async def test_required_unless_field_required_when_condition_not_met():
    from arvel.validation.rules.conditional import RequiredUnless
    from arvel.validation.validator import Validator

    validator = Validator()
    with pytest.raises(ValidationError) as exc_info:
        await validator.validate(
            {"role": "admin"},
            {"backup_email": [RequiredUnless("role", "guest")]},
        )
    assert any(e.field == "backup_email" for e in exc_info.value.errors)


async def test_required_unless_field_optional_when_condition_met():
    from arvel.validation.rules.conditional import RequiredUnless
    from arvel.validation.validator import Validator

    validator = Validator()
    result = await validator.validate(
        {"role": "guest"},
        {"backup_email": [RequiredUnless("role", "guest")]},
    )
    assert result is not None


# ──── RequiredWith ────


async def test_required_with_field_required_when_other_present():
    from arvel.validation.rules.conditional import RequiredWith
    from arvel.validation.validator import Validator

    validator = Validator()
    with pytest.raises(ValidationError) as exc_info:
        await validator.validate(
            {"phone": "+1234567890"},
            {"phone_country_code": [RequiredWith("phone")]},
        )
    assert any(e.field == "phone_country_code" for e in exc_info.value.errors)


async def test_required_with_field_optional_when_other_absent():
    from arvel.validation.rules.conditional import RequiredWith
    from arvel.validation.validator import Validator

    validator = Validator()
    result = await validator.validate(
        {},
        {"phone_country_code": [RequiredWith("phone")]},
    )
    assert result is not None


# ──── ProhibitedIf ────


async def test_prohibited_if_field_prohibited_when_condition_met():
    from arvel.validation.rules.conditional import ProhibitedIf
    from arvel.validation.validator import Validator

    validator = Validator()
    with pytest.raises(ValidationError) as exc_info:
        await validator.validate(
            {"account_type": "free", "premium_features": "yes"},
            {"premium_features": [ProhibitedIf("account_type", "free")]},
        )
    assert any(e.field == "premium_features" for e in exc_info.value.errors)


async def test_prohibited_if_field_allowed_when_condition_not_met():
    from arvel.validation.rules.conditional import ProhibitedIf
    from arvel.validation.validator import Validator

    validator = Validator()
    result = await validator.validate(
        {"account_type": "premium", "premium_features": "yes"},
        {"premium_features": [ProhibitedIf("account_type", "free")]},
    )
    assert result["premium_features"] == "yes"


# ──── Missing Condition Field ────


async def test_required_if_condition_field_missing_skips_validation():
    """Missing condition field is treated as 'condition not met'."""
    from arvel.validation.rules.conditional import RequiredIf
    from arvel.validation.validator import Validator

    validator = Validator()
    result = await validator.validate(
        {},
        {"permissions": [RequiredIf("role", "admin")]},
    )
    assert result is not None


# ──── Short-Circuit Behavior ────


async def test_conditional_short_circuits_other_rules():
    """When conditional rule's condition is not met, other rules on the field are skipped."""
    from arvel.validation.rules.conditional import RequiredIf
    from arvel.validation.validator import Validator

    class AlwaysFail:
        def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
            return False

        def message(self) -> str:
            return "Should never fire."

    validator = Validator()
    result = await validator.validate(
        {"role": "user"},
        {"permissions": [RequiredIf("role", "admin"), AlwaysFail()]},
    )
    assert result is not None
