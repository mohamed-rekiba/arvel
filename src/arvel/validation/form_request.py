"""FormRequest — combines authorization, validation, and post-processing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.validation.exceptions import AuthorizationFailedError
from arvel.validation.validator import Validator

if TYPE_CHECKING:
    from starlette.requests import Request

    from arvel.validation.rule import AsyncRule, Rule


class FormRequest:
    """Base class for form request objects.

    Subclasses override `authorize()`, `rules()`, and optionally
    `messages()` and `after_validation()`.
    """

    def authorize(self, request: Request | None) -> bool:
        """Return True if the request is authorized, False otherwise."""
        return True

    def rules(self) -> dict[str, list[Rule | AsyncRule]]:
        """Return validation rules keyed by field name."""
        return {}

    def messages(self) -> dict[str, str]:
        """Return custom error messages keyed by 'field.RuleName'."""
        return {}

    def after_validation(self, data: dict[str, Any]) -> dict[str, Any]:
        """Post-validation hook. Transform or enrich the validated data."""
        return data

    async def validate_request(
        self,
        *,
        request: Request | None,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Run authorization, validation, and after-hook in order."""
        if not self.authorize(request):
            raise AuthorizationFailedError()

        field_rules = self.rules()
        custom_messages = self.messages()

        validator = Validator()
        validated = await validator.validate(data, field_rules, messages=custom_messages)

        return self.after_validation(validated)
