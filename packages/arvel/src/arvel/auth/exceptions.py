"""Auth subsystem exceptions.

Exceptions split into two layers:

- **HTTP-shaped** (``UnauthenticatedException``, ``AuthorizationException``)
  carry a ``status_code`` so the framework's exception-to-problem-details
  layer can map them with no extra glue.
- **Domain** (``InvalidCredentialsError`` and friends) signal the broker
  outcome to the controller, which decides on the HTTP shape (401 / 403 /
  409 / 422). Brokers never know about HTTP.
"""

from __future__ import annotations


class AuthConfigError(Exception):
    """Raised when ``config.auth`` is invalid or references an unknown driver/guard."""


class UnauthenticatedException(Exception):  # noqa: N818
    """Request is not authenticated. Maps to HTTP 401."""

    status_code: int = 401


class AuthorizationException(Exception):  # noqa: N818
    """Action is not authorized. Maps to HTTP 403."""

    status_code: int = 403


class AuthError(Exception):
    """Base class for broker-layer domain errors that are NOT HTTP 5xx."""


class EmailAlreadyRegisteredError(AuthError):
    """Register: email is already in the users table. → HTTP 409."""


class EmailNotVerifiedError(AuthError):
    """Login: ``email_verified_at`` is null. → HTTP 422."""


class InvalidCredentialsError(AuthError):
    """Login or refresh: email unknown / password mismatch / refresh token unknown. → HTTP 401."""


class AccountSuspendedError(AuthError):
    """Login: ``suspended_at`` is non-null. → HTTP 403."""


class TokenReuseDetectedError(AuthError):
    """Refresh: the supplied cookie was already rotated. → HTTP 401.

    Triggers entire-family revocation in :meth:`AuthBroker.refresh`.
    """


class PasswordResetTokenInvalidError(AuthError):
    """Reset: token is unknown, expired, or already burned. → HTTP 422.

    Maps to a field-level ``token`` validation error so the SPA can render
    the message inline above the form.
    """


class EmailVerificationInvalidError(AuthError):
    """Verify: signed URL is tampered, expired, or for an email that has changed. → HTTP 401."""


__all__ = [
    "AccountSuspendedError",
    "AuthConfigError",
    "AuthError",
    "AuthorizationException",
    "EmailAlreadyRegisteredError",
    "EmailNotVerifiedError",
    "EmailVerificationInvalidError",
    "InvalidCredentialsError",
    "PasswordResetTokenInvalidError",
    "TokenReuseDetectedError",
    "UnauthenticatedException",
]
