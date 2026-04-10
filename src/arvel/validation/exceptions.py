"""Validation layer exceptions."""

from __future__ import annotations

from typing import TypedDict


class FieldErrorDict(TypedDict):
    """Serialized representation of a single field validation error."""

    field: str
    rule: str
    message: str


class ValidationErrorDict(TypedDict):
    """Serialized representation of a validation error response."""

    message: str
    errors: list[FieldErrorDict]


class FieldError:
    """Single field validation error."""

    __slots__ = ("field", "message", "rule")

    def __init__(self, *, field: str, rule: str, message: str) -> None:
        self.field = field
        self.rule = rule
        self.message = message

    def to_dict(self) -> FieldErrorDict:
        return {"field": self.field, "rule": self.rule, "message": self.message}


class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(
        self,
        errors: list[FieldError],
        message: str = "The given data was invalid.",
    ) -> None:
        self.errors = errors
        self.detail = message
        super().__init__(message)

    def to_dict(self) -> ValidationErrorDict:
        return {
            "message": self.detail,
            "errors": [e.to_dict() for e in self.errors],
        }


class AuthorizationFailedError(Exception):
    """Raised when form request authorization fails."""

    def __init__(self, message: str = "This action is unauthorized.") -> None:
        self.detail = message
        super().__init__(message)
