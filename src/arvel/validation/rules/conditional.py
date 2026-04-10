"""Conditional validation rules.

These rules check conditions against other fields in the data and
control whether a field is required, optional, or prohibited.
"""

from __future__ import annotations

from typing import Any


class ConditionalRule:
    """Base marker for conditional rules.

    Conditional rules expose `condition_met(data)` to signal whether
    the field's validation should proceed. When the condition is not met,
    the Validator skips all remaining rules on the field (short-circuit).
    """

    def condition_met(self, data: dict[str, Any]) -> bool:
        raise NotImplementedError

    def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
        raise NotImplementedError

    def message(self) -> str:
        raise NotImplementedError


class RequiredIf(ConditionalRule):
    """Field is required when another field equals a specific value."""

    def __init__(self, other_field: str, other_value: Any) -> None:
        self._other_field = other_field
        self._other_value = other_value

    def condition_met(self, data: dict[str, Any]) -> bool:
        return data.get(self._other_field) == self._other_value

    def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
        return value is not None and value != ""

    def message(self) -> str:
        return f"This field is required when {self._other_field} is {self._other_value}."


class RequiredUnless(ConditionalRule):
    """Field is required unless another field equals a specific value."""

    def __init__(self, other_field: str, other_value: Any) -> None:
        self._other_field = other_field
        self._other_value = other_value

    def condition_met(self, data: dict[str, Any]) -> bool:
        return data.get(self._other_field) != self._other_value

    def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
        return value is not None and value != ""

    def message(self) -> str:
        return f"This field is required unless {self._other_field} is {self._other_value}."


class RequiredWith(ConditionalRule):
    """Field is required when another field is present."""

    def __init__(self, other_field: str) -> None:
        self._other_field = other_field

    def condition_met(self, data: dict[str, Any]) -> bool:
        other = data.get(self._other_field)
        return other is not None and other != ""

    def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
        return value is not None and value != ""

    def message(self) -> str:
        return f"This field is required when {self._other_field} is present."


class ProhibitedIf(ConditionalRule):
    """Field must not be present when another field equals a specific value."""

    def __init__(self, other_field: str, other_value: Any) -> None:
        self._other_field = other_field
        self._other_value = other_value

    def condition_met(self, data: dict[str, Any]) -> bool:
        return data.get(self._other_field) == self._other_value

    def passes(self, attribute: str, value: Any, data: dict[str, Any]) -> bool:
        return value is None or value == ""

    def message(self) -> str:
        return f"This field is prohibited when {self._other_field} is {self._other_value}."
