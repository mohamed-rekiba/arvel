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


_WILDCARD = "*"


def _index_into(cursor: object, seg: str) -> tuple[object, bool]:
    """Resolve one non-wildcard path segment; returns (value, present)."""
    if isinstance(cursor, Mapping):
        mapping = cast("Mapping[object, object]", cursor)
        if seg in mapping:
            return mapping[seg], True
    if isinstance(cursor, list):
        items = cast("list[object]", cursor)
        if seg.lstrip("-").isdigit():
            idx = int(seg)
            if -len(items) <= idx < len(items):
                return items[idx], True
    return None, False


def _expand_wildcard(cursor: object) -> list[tuple[str, object]]:
    if isinstance(cursor, list):
        items = cast("list[object]", cursor)
        return [(str(i), el) for i, el in enumerate(items)]
    if isinstance(cursor, Mapping):
        mapping = cast("Mapping[object, object]", cursor)
        return [(str(key), val) for key, val in mapping.items()]
    return []


def resolve_targets(field: str, data: Mapping[str, object]) -> list[tuple[str, object, bool]]:
    """Expand a (possibly dotted/wildcard) field into concrete ``(path, value, present)`` targets.

    A non-wildcard path always yields one target even when missing (value ``None``,
    ``present=False``) so `required`/`present` can fire. A `*` only iterates the
    entries that actually exist, so a missing collection yields nothing — matching
    Laravel's wildcard behavior.
    """
    if _WILDCARD not in field and "." not in field:
        return [(field, data.get(field), field in data)]
    frontier: list[tuple[list[str], object, bool]] = [([], data, True)]
    for seg in field.split("."):
        nxt: list[tuple[list[str], object, bool]] = []
        for parts, cursor, _present in frontier:
            if seg == _WILDCARD:
                nxt.extend(([*parts, key], el, True) for key, el in _expand_wildcard(cursor))
            else:
                value, present = _index_into(cursor, seg)
                nxt.append(([*parts, seg], value, present))
        frontier = nxt
    return [(".".join(parts), value, present) for parts, value, present in frontier]


class Validator:
    """Apply string rules to a payload mapping, including nested/wildcard paths (`items.*.id`)."""

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
            nested = _WILDCARD in field or "." in field
            for path, value, present in resolve_targets(field, self._data):
                scoped = self._scoped_data(path, value, present=present) if nested else self._data
                details.extend(await self._run_target(field, path, value, expressions, scoped))
        return details

    def _scoped_data(self, path: str, value: object, *, present: bool) -> Mapping[str, object]:
        """Full payload plus the concrete dotted path as a key, so presence rules see it."""
        scoped = dict(self._data)
        if present:
            scoped[path] = value
        else:
            scoped.pop(path, None)
        return scoped

    async def _run_target(
        self,
        field: str,
        path: str,
        value: object,
        expressions: Sequence[str],
        data: Mapping[str, object],
    ) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        # `bail` stops this target at its first failure (Laravel semantics).
        stop_on_first = any(parse_rule_expression(expr)[0] == "bail" for expr in expressions)
        for expression in expressions:
            rule_name, params = parse_rule_expression(expression)
            if rule_name == "bail":
                continue
            handler = RULE_HANDLERS.get(rule_name)
            if handler is None:
                out.append({"field": path, "issue": f"Unknown validation rule {rule_name!r}."})
                continue
            raw_outcome = handler(path, value, params, data, self._request)
            if asyncio.iscoroutine(raw_outcome):
                failure_message = await raw_outcome
            else:
                failure_message = cast("str | None", raw_outcome)
            if failure_message is None:
                continue
            issue = self._message_for(field, path, rule_name, failure_message)
            out.append({"field": path, "issue": issue})
            if stop_on_first:
                break
        return out

    def _message_for(self, field: str, path: str, rule_name: str, failure: str) -> str:
        """Override lookup tries the concrete path first, then the wildcard form (`items.*.id`)."""
        issue = self._messages.get(f"{path}.{rule_name}")
        if issue is None and field != path:
            issue = self._messages.get(f"{field}.{rule_name}")
        if issue is None:
            issue = failure
        label = self._attributes.get(path)
        if label is None and field != path:
            label = self._attributes.get(field)
        if label is not None and label != path and label not in issue:
            issue = issue.replace(path, label, 1)
        return issue
