"""Conditional rule helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

ConditionCallback = Callable[[Mapping[str, object]], bool]


@dataclass(frozen=True, slots=True)
class ConditionalRule:
    field: str
    rules: str | Sequence[str]
    condition: ConditionCallback


class Rule:
    """Laravel-style rule builder helpers."""

    @staticmethod
    def sometimes(
        field: str,
        rules: str | Sequence[str],
        condition: ConditionCallback,
    ) -> ConditionalRule:
        return ConditionalRule(field=field, rules=rules, condition=condition)


__all__ = ["ConditionalRule", "Rule"]
