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
    """Laravel-style rule builder helpers.

    The builders return rule-expression strings that slot into the same
    pipe-separated pipeline as hand-written rules — values are comma-joined, so
    a value containing a comma isn't supported (use a custom rule for that).
    """

    @staticmethod
    def sometimes(
        field: str,
        rules: str | Sequence[str],
        condition: ConditionCallback,
    ) -> ConditionalRule:
        return ConditionalRule(field=field, rules=rules, condition=condition)

    @staticmethod
    def in_(*values: object) -> str:
        return "in:" + ",".join(str(v) for v in values)

    @staticmethod
    def not_in(*values: object) -> str:
        return "not_in:" + ",".join(str(v) for v in values)

    @staticmethod
    def exists(table: str, column: str) -> str:
        return f"exists:{table},{column}"

    @staticmethod
    def unique(
        table: str,
        column: str,
        *,
        ignore: object | None = None,
        id_column: str = "id",
    ) -> str:
        if ignore is None:
            return f"unique:{table},{column}"
        return f"unique:{table},{column},{ignore},{id_column}"

    @staticmethod
    def required_if(field: str, *values: object) -> str:
        return f"required_if:{field}," + ",".join(str(v) for v in values)

    @staticmethod
    def required_unless(field: str, *values: object) -> str:
        return f"required_unless:{field}," + ",".join(str(v) for v in values)


__all__ = ["ConditionalRule", "Rule"]
