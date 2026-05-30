"""Auth lifecycle events — dispatched by ``arvel.auth`` services.

Every service emits domain events (Laravel ``Auth\\Events`` parity) so
listeners can audit, send mail, broadcast, or extend behaviour without
touching service internals.

Events carry ``user_id``, ``email``, and ``occurred_at``.  IP / user-agent
belong in access logs or a request-audit middleware, not domain events.
"""

from __future__ import annotations

from datetime import datetime

from arvel.events.event import Event


class AuthEvent(Event):
    """Shared payload for every auth lifecycle event.

    ``user_id`` is optional because the failure path (:class:`LoginFailed`,
    :class:`PasswordResetRequested` for an unknown email) fires even when
    the actor never resolved to a row — the audit row stays useful by
    recording the attempted email.
    """

    user_id: str | None
    email: str
    occurred_at: datetime


class Registered(AuthEvent):
    """Fired by :meth:`AuthService.register` after a successful create."""


class LoggedIn(AuthEvent):
    """Fired by :meth:`AuthService.login` after a successful credential check."""


class LoginFailed(AuthEvent):
    """Fired by :meth:`AuthService.login` on every failure path."""


class LoggedOut(AuthEvent):
    """Fired by :meth:`AuthService.logout` after revoking the refresh cookie."""


class EmailVerified(AuthEvent):
    """Fired by :meth:`EmailVerificationService.consume` after marking the row."""


class PasswordResetRequested(AuthEvent):
    """Fired by :meth:`PasswordService.forgot` for every known-user request.

    ``reset_token`` carries the plaintext token to the mail listener.
    The audit listener must not persist this field.
    """

    reset_token: str | None = None


class PasswordResetCompleted(AuthEvent):
    """Fired by :meth:`PasswordService.reset` after a successful reset."""


class TokenReuseDetected(AuthEvent):
    """Fired by :meth:`AuthService.revoke_family` when a rotated token is re-used."""


__all__ = [
    "AuthEvent",
    "EmailVerified",
    "LoggedIn",
    "LoggedOut",
    "LoginFailed",
    "PasswordResetCompleted",
    "PasswordResetRequested",
    "Registered",
    "TokenReuseDetected",
]
