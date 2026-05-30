"""Validate payload dicts against Laravel-style rule strings."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from arvel.validation.rule import ConditionalRule
from arvel.validation.rules import RULE_HANDLERS, parse_rule_expression


def expand_rule_expressions(field_rules: str | Sequence[str]) -> list[str]:
    """Expand ``required|digits:16`` or rule lists into individual expressions."""
    if isinstance(field_rules, str):
        return [part.strip() for part in field_rules.split("|") if part.strip()]
    return [str(rule) for rule in field_rules]


def merge_rules(
    base: Mapping[str, str | Sequence[str]],
    conditional: Sequence[ConditionalRule],
    data: Mapping[str, object],
) -> dict[str, str | list[str]]:
    """Apply active ``sometimes`` rules onto a base rules mapping."""
    merged: dict[str, str | list[str]] = {
        field: list(expressions)
        if isinstance(expressions, list)
        else expand_rule_expressions(expressions)
        for field, expressions in base.items()
    }
    for spec in conditional:
        if not spec.condition(data):
            continue
        expressions = expand_rule_expressions(spec.rules)
        existing = merged.get(spec.field)
        if existing is None:
            merged[spec.field] = expressions
        else:
            merged[spec.field] = [*existing, *expressions]
    return merged


class Validator:
    """Apply string rules to a flat payload mapping."""

    def __init__(
        self,
        data: Mapping[str, object],
        *,
        request: Any | None = None,
        messages: Mapping[str, str] | None = None,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        self._data = data
        self._request = request
        self._messages = dict(messages or {})
        self._attributes = dict(attributes or {})
        self._conditional: list[ConditionalRule] = []

    def sometimes(
        self,
        field: str,
        rules: str | Sequence[str],
        condition: Callable[[Mapping[str, object]], bool],
    ) -> Validator:
        self._conditional.append(ConditionalRule(field=field, rules=rules, condition=condition))
        return self

    def add(self, spec: ConditionalRule) -> Validator:
        self._conditional.append(spec)
        return self

    async def validate(
        self,
        rules: Mapping[str, str | Sequence[str]] | None = None,
    ) -> list[dict[str, str]]:
        merged = merge_rules(rules or {}, self._conditional, self._data)
        details: list[dict[str, str]] = []
        for field, field_rules in merged.items():
            expressions = (
                field_rules
                if isinstance(field_rules, list)
                else expand_rule_expressions(field_rules)
            )
            value = self._data.get(field)
            for expression in expressions:
                rule_name, params = parse_rule_expression(expression)
                handler = RULE_HANDLERS.get(rule_name)
                if handler is None:
                    issue = f"Unknown validation rule {rule_name!r}."
                    details.append({"field": field, "issue": issue})
                    continue
                raw_outcome = handler(field, value, params, self._data, self._request)
                failure_message: str | None
                if asyncio.iscoroutine(raw_outcome):
                    failure_message = await raw_outcome
                else:
                    failure_message = cast("str | None", raw_outcome)
                if failure_message is None:
                    continue
                message_key = f"{field}.{rule_name}"
                issue = self._messages.get(message_key, failure_message)
                label = self._attributes.get(field, field)
                if label != field and label not in issue:
                    issue = issue.replace(field, label, 1)
                details.append({"field": field, "issue": issue})
        return details
