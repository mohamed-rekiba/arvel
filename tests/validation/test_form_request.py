"""Tests for FormRequest — Story 1: Form Request Objects.

Tests must compile but FAIL until implementation exists.
"""

from __future__ import annotations

from typing import Any

import pytest

# ──── FormRequest Authorization ────


async def test_form_request_authorize_returns_false_raises_403():
    from arvel.validation.form_request import FormRequest

    class DeniedRequest(FormRequest):
        def authorize(self, request: Any) -> bool:
            return False

        def rules(self) -> dict[str, list]:
            return {}

    fr = DeniedRequest()
    from arvel.validation.exceptions import AuthorizationFailedError

    with pytest.raises(AuthorizationFailedError):
        await fr.validate_request(request=None, data={"name": "Alice"})


async def test_form_request_authorize_returns_true_proceeds():
    from arvel.validation.form_request import FormRequest

    class AllowedRequest(FormRequest):
        def authorize(self, request: Any) -> bool:
            return True

        def rules(self) -> dict[str, list]:
            return {}

    fr = AllowedRequest()
    result = await fr.validate_request(request=None, data={"name": "Alice"})
    assert result == {"name": "Alice"}


# ──── Authorization Runs Before Validation ────


async def test_authorize_runs_before_validation():
    """Authorization should fail before validation even starts."""
    from arvel.validation.exceptions import AuthorizationFailedError
    from arvel.validation.form_request import FormRequest

    validation_ran = False

    class DeniedWithRules(FormRequest):
        def authorize(self, request: Any) -> bool:
            return False

        def rules(self) -> dict[str, list]:
            nonlocal validation_ran
            validation_ran = True
            return {"name": []}

    fr = DeniedWithRules()
    with pytest.raises(AuthorizationFailedError):
        await fr.validate_request(request=None, data={"name": "Alice"})

    assert not validation_ran


# ──── Validation with Rules ────


async def test_form_request_validation_fails_with_rules():
    from arvel.validation.exceptions import ValidationError
    from arvel.validation.form_request import FormRequest

    class FailRule:
        def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
            return False

        def message(self) -> str:
            return "Field is invalid."

    class StrictRequest(FormRequest):
        def authorize(self, request: Any) -> bool:
            return True

        def rules(self) -> dict[str, list]:
            return {"name": [FailRule()]}

    fr = StrictRequest()
    with pytest.raises(ValidationError) as exc_info:
        await fr.validate_request(request=None, data={"name": ""})
    assert len(exc_info.value.errors) == 1
    assert exc_info.value.errors[0].field == "name"


# ──── Custom Messages ────


async def test_form_request_custom_messages():
    from arvel.validation.exceptions import ValidationError
    from arvel.validation.form_request import FormRequest

    class FailRule:
        def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
            return False

        def message(self) -> str:
            return "Default message."

    class CustomMsgRequest(FormRequest):
        def authorize(self, request: Any) -> bool:
            return True

        def rules(self) -> dict[str, list]:
            return {"email": [FailRule()]}

        def messages(self) -> dict[str, str]:
            return {"email.FailRule": "Please provide a valid email."}

    fr = CustomMsgRequest()
    with pytest.raises(ValidationError) as exc_info:
        await fr.validate_request(request=None, data={"email": ""})
    assert exc_info.value.errors[0].message == "Please provide a valid email."


# ──── After Validation Hook ────


async def test_form_request_after_validation_hook():
    from arvel.validation.form_request import FormRequest

    class HookRequest(FormRequest):
        def authorize(self, request: Any) -> bool:
            return True

        def rules(self) -> dict[str, list]:
            return {}

        def after_validation(self, data: dict[str, Any]) -> dict[str, Any]:
            data["name"] = data["name"].strip().title()
            return data

    fr = HookRequest()
    result = await fr.validate_request(request=None, data={"name": "  alice  "})
    assert result["name"] == "Alice"


# ──── Dynamic Rules ────


async def test_form_request_dynamic_rules_evaluated_at_request_time():
    from arvel.validation.exceptions import ValidationError
    from arvel.validation.form_request import FormRequest

    call_count = 0

    class MinLen:
        def __init__(self, n: int) -> None:
            self._n = n

        def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
            return isinstance(value, str) and len(value) >= self._n

        def message(self) -> str:
            return f"Too short (min {self._n})."

    class DynamicRequest(FormRequest):
        def authorize(self, request: Any) -> bool:
            return True

        def rules(self) -> dict[str, list]:
            nonlocal call_count
            call_count += 1
            return {"name": [MinLen(3)]}

    fr = DynamicRequest()

    with pytest.raises(ValidationError):
        await fr.validate_request(request=None, data={"name": "Al"})
    assert call_count == 1

    result = await fr.validate_request(request=None, data={"name": "Alice"})
    assert call_count == 2
    assert result["name"] == "Alice"
