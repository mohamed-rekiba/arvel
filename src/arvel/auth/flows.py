"""arvel.auth.flows — email-verification + password-reset tokens (signed URLs).

A purpose-tagged, time-limited token over ``arvel.security.Signer`` (itsdangerous). The token
carries ``<purpose>:<user_id>`` signed with the app key; verifying checks the signature, the
expiry, and that the purpose matches — so a verification link can't be replayed as a reset.
Route handlers (send link / confirm) are app-side. Grounded in knowledge/port/15.
"""

from __future__ import annotations

from typing import Any


def _signer(secret: str) -> Any:
    from arvel.security import Signer

    return Signer(secret)


def _issue(purpose: str, user_id: int, secret: str) -> str:
    return str(_signer(secret).sign(f"{purpose}:{user_id}"))


def _verify(token: str, purpose: str, secret: str, max_age: int) -> int | None:
    try:
        value = _signer(secret).unsign(token, max_age=max_age)
    except Exception:
        return None
    prefix, _, raw_id = str(value).partition(":")
    if prefix != purpose or not raw_id.isdigit():
        return None
    return int(raw_id)


def email_verification_token(user_id: int, secret: str) -> str:
    """A signed token proving ownership of an email address."""
    return _issue("verify", user_id, secret)


def verify_email_token(token: str, secret: str, *, max_age: int = 86400) -> int | None:
    """The user id if the verification token is valid + unexpired, else ``None`` (24h default)."""
    return _verify(token, "verify", secret, max_age)


def password_reset_token(user_id: int, secret: str) -> str:
    """A signed token authorizing a password reset."""
    return _issue("reset", user_id, secret)


def verify_password_reset_token(token: str, secret: str, *, max_age: int = 3600) -> int | None:
    """The user id if the reset token is valid + unexpired, else ``None`` (1h default)."""
    return _verify(token, "reset", secret, max_age)
