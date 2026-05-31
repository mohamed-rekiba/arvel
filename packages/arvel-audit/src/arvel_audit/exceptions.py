"""arvel-audit exceptions."""

from __future__ import annotations


class AuditError(Exception):
    """Base for every arvel-audit error."""


class InvalidAuditAction(AuditError):
    """Raised when a query filters on an action outside the known set."""

    def __init__(self, action: str, valid: tuple[str, ...]) -> None:
        self.action = action
        self.valid = valid
        super().__init__(f"Unknown audit action {action!r}. Valid actions: {', '.join(valid)}.")


class MissingActivityDescription(AuditError):
    """Raised when an activity is saved without calling ``log()`` first."""

    def __init__(self) -> None:
        super().__init__("Call .log(description) before .save() on an activity recorder.")


__all__ = ["AuditError", "InvalidAuditAction", "MissingActivityDescription"]
