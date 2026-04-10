"""Validator engine — orchestrates rule execution and error collection."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from arvel.validation.exceptions import FieldError, ValidationError

if TYPE_CHECKING:
    from arvel.validation.rule import AsyncRule, Rule


class Validator:
    """Run validation rules against data, collecting all errors."""

    async def validate(
        self,
        data: dict[str, Any],
        rules: dict[str, list[Rule | AsyncRule]],
        *,
        messages: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        errors: list[FieldError] = []
        custom_messages = messages or {}

        for field, field_rules in rules.items():
            value = data.get(field)
            skip_remaining = False

            for rule in field_rules:
                if skip_remaining:
                    break

                should_skip, field_errors = await self._run_rule(
                    rule, field, value, data, custom_messages
                )
                errors.extend(field_errors)

                if should_skip:
                    skip_remaining = True

        if errors:
            raise ValidationError(errors)

        return data

    async def _run_rule(
        self,
        rule: Rule | AsyncRule,
        field: str,
        value: Any,
        data: dict[str, Any],
        custom_messages: dict[str, str],
    ) -> tuple[bool, list[FieldError]]:
        """Run a single rule and return (should_skip_remaining, errors).

        Conditional rules can signal skip via a `should_skip` attribute.
        """
        from arvel.validation.rules.conditional import ConditionalRule

        if isinstance(rule, ConditionalRule):
            should_apply = rule.condition_met(data)
            if not should_apply:
                return True, []

            if not rule.passes(field, value, data):
                rule_name = type(rule).__name__
                msg = self._resolve_message(field, rule_name, rule.message(), custom_messages)
                return False, [FieldError(field=field, rule=rule_name, message=msg)]
            return False, []

        passes = rule.passes(field, value, data)
        if inspect.isawaitable(passes):
            passes = await passes

        if not passes:
            rule_name = type(rule).__name__
            msg = self._resolve_message(field, rule_name, rule.message(), custom_messages)
            return False, [FieldError(field=field, rule=rule_name, message=msg)]

        return False, []

    @staticmethod
    def _resolve_message(
        field: str,
        rule_name: str,
        default_message: str,
        custom_messages: dict[str, str],
    ) -> str:
        key = f"{field}.{rule_name}"
        return custom_messages.get(key, default_message)
