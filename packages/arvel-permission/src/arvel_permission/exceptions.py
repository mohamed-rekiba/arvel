"""Typed exceptions for arvel-permission."""

from __future__ import annotations


class RoleDoesNotExistError(Exception):
    """Raised when a role name cannot be found."""


class PermissionDoesNotExistError(Exception):
    """Raised when a permission name cannot be found."""


class UnauthorizedException(Exception):  # noqa: N818 — Spatie API parity; callers expect this exact name
    """Raised by middleware when a user lacks the required role or permission.

    status_code is 401 when there is no authenticated user, 403 when the user
    exists but lacks the required role/permission.
    """

    def __init__(self, *, status_code: int = 403, message: str = "") -> None:
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code


# Spatie parity aliases — Spatie raises RoleDoesNotExist / PermissionDoesNotExist
RoleDoesNotExist = RoleDoesNotExistError
PermissionDoesNotExist = PermissionDoesNotExistError
