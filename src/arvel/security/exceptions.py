"""Security exceptions."""

from __future__ import annotations


class SecurityError(Exception):
    """Base exception for the security module."""


class DecryptionError(SecurityError):
    """Decryption failed — MAC verification failure or corrupted payload."""


class HashingError(SecurityError):
    """Password hashing or verification failed."""


class AuthenticationError(SecurityError):
    """Authentication failed — invalid credentials, expired token, etc."""

    def __init__(
        self, message: str = "Authentication failed", *, code: str = "AUTH_FAILED"
    ) -> None:
        super().__init__(message)
        self.code = code


class AuthorizationError(SecurityError):
    """Authorization failed — user lacks permission."""

    def __init__(self, message: str = "Forbidden", *, action: str = "", resource: str = "") -> None:
        super().__init__(message)
        self.action = action
        self.resource = resource
