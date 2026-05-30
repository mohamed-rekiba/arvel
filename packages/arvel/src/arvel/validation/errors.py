"""Validation rule failures."""

from __future__ import annotations


class ValidationRuleError(Exception):
    """Raised when a single rule fails; carries field and rule name for messaging."""

    def __init__(self, field: str, rule: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.rule = rule
        self.message = message
