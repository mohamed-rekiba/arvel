"""arvel.auth.two_factor — TOTP two-factor authentication on **pyotp** (mandated engine).

Parity glue only: pyotp owns the TOTP algorithm; arvel wraps secret generation, the
``otpauth://`` provisioning URI (for authenticator-app QR codes), code verification (with a
small clock-skew window), and one-time recovery codes. pyotp is imported lazily (the ``[2fa]``
extra), so ``import arvel`` stays light. Grounded in knowledge/port/15-auth-authorization.md.

The Fortify-parity lifecycle below (``enable_two_factor``/``confirm_two_factor``/
``verify_two_factor``/``disable_two_factor``/``regenerate_recovery_codes``) stores three plain
attributes on the ``user`` you pass in: ``two_factor_secret``, ``two_factor_recovery_codes``
(a list of *hashed* codes), and ``two_factor_confirmed_at``. arvel does not encrypt these for you —
exactly like Laravel Fortify, your user model owns that by declaring the model casts:

    class User(Model, Authenticatable):
        __casts__ = {
            "two_factor_secret": "encrypted",
            "two_factor_recovery_codes": "encrypted:array",
            "two_factor_confirmed_at": "datetime",
        }

(and a migration adding those three nullable columns — arvel ships no migration for them, since the
column lives on *your* user model, not a framework table.) Without those casts the columns hold their
values in plaintext; add them before shipping 2FA.

The login-challenge state machine (``requires_two_factor_challenge``/``begin_two_factor_challenge``/
``pending_two_factor_user_id``/``complete_two_factor_challenge``) is the guard hook: call
``begin_two_factor_challenge`` from your login flow instead of a full login when 2FA is confirmed —
it stashes the pending user id in the session and raises ``TwoFactorRequired``. The actual
``/two-factor-challenge`` route (render a code form, call ``complete_two_factor_challenge``, then
finish the *real* login e.g. ``SessionGuard.login``) is app-side; arvel ships the state, not the route.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any, cast


class TwoFactor:
    """TOTP helpers over pyotp (RFC 6238). The secret is stored per user; codes are 6-digit."""

    @staticmethod
    def generate_secret() -> str:
        """A fresh base32 TOTP secret to store for the user."""
        import pyotp

        return str(pyotp.random_base32())

    @staticmethod
    def provisioning_uri(secret: str, account_name: str, *, issuer: str = "arvel") -> str:
        """An ``otpauth://`` URI to render as a QR code in an authenticator app."""
        import pyotp

        totp: Any = pyotp.TOTP(secret)  # pyotp is only partially typed — funnel through Any
        return str(totp.provisioning_uri(name=account_name, issuer_name=issuer))

    @staticmethod
    def verify(secret: str, code: str, *, valid_window: int = 1) -> bool:
        """Is ``code`` valid for ``secret`` now (± ``valid_window`` 30s steps of skew)?"""
        import pyotp

        return bool(pyotp.TOTP(secret).verify(code, valid_window=valid_window))

    @staticmethod
    def current_code(secret: str) -> str:
        """The code valid at this instant (for tests / display)."""
        import pyotp

        return str(pyotp.TOTP(secret).now())

    @staticmethod
    def recovery_codes(count: int = 8) -> list[str]:
        """Single-use recovery codes to store (hashed) alongside the secret."""
        return [secrets.token_hex(5) for _ in range(count)]


def _hasher(explicit: Any = None) -> Any:
    if explicit is not None:
        return explicit
    from arvel.security import resolve_hasher

    return resolve_hasher()


@dataclass
class TwoFactorEnrollment:
    """The one-time output of :func:`enable_two_factor` — show both to the user, then discard;
    only the recovery codes' *hashes* are persisted."""

    provisioning_uri: str
    recovery_codes: list[str]


async def enable_two_factor(
    user: Any,
    *,
    account_name: str | None = None,
    issuer: str = "arvel",
    recovery_code_count: int = 8,
    hasher: Any = None,
) -> TwoFactorEnrollment:
    """Provision 2FA for ``user``: a fresh TOTP secret + a set of hashed recovery codes — but **not**
    confirmed (``two_factor_confirmed_at`` stays unset until :func:`confirm_two_factor` verifies a
    live code). Returns the provisioning URI (render as a QR) and the recovery codes in
    **plaintext**, once; only their hashes are stored.
    """
    hsh = _hasher(hasher)
    secret = TwoFactor.generate_secret()
    codes = TwoFactor.recovery_codes(recovery_code_count)
    name = account_name or getattr(user, "email", None) or str(getattr(user, "id", ""))

    user.two_factor_secret = secret
    user.two_factor_recovery_codes = [hsh.make(code) for code in codes]
    user.two_factor_confirmed_at = None  # explicit: enabling never auto-confirms
    await user.save()

    uri = TwoFactor.provisioning_uri(secret, name, issuer=issuer)
    return TwoFactorEnrollment(provisioning_uri=uri, recovery_codes=codes)


async def confirm_two_factor(user: Any, code: str) -> bool:
    """Confirm enrollment: verify a live TOTP ``code`` against the stored secret and, on success,
    stamp ``two_factor_confirmed_at``. 2FA is not enforced at login before this has run."""
    secret = getattr(user, "two_factor_secret", None)
    if not secret or not TwoFactor.verify(secret, code):
        return False
    from arvel.dates import now

    user.two_factor_confirmed_at = now()
    await user.save()
    return True


async def disable_two_factor(user: Any) -> None:
    """Turn 2FA off entirely: clears the secret, the recovery codes, and the confirmation timestamp."""
    user.two_factor_secret = None
    user.two_factor_recovery_codes = None
    user.two_factor_confirmed_at = None
    await user.save()


async def verify_two_factor(user: Any, code: str, *, hasher: Any = None) -> bool:
    """Verify a login-time ``code``: a live TOTP code, **or** a recovery code — consumed single-use
    on match (removed from the stored set and re-persisted), so it can never be replayed."""
    secret = getattr(user, "two_factor_secret", None)
    if secret and TwoFactor.verify(secret, code):
        return True
    return await _consume_recovery_code(user, code, hasher=_hasher(hasher))


async def _consume_recovery_code(user: Any, code: str, *, hasher: Any) -> bool:
    hashed_codes = list(getattr(user, "two_factor_recovery_codes", None) or [])
    for stored in hashed_codes:
        if hasher.check(code, stored):
            user.two_factor_recovery_codes = [h for h in hashed_codes if h != stored]
            await user.save()
            return True
    return False


async def regenerate_recovery_codes(user: Any, *, count: int = 8, hasher: Any = None) -> list[str]:
    """Replace ``user``'s recovery codes with a fresh set — the old codes are invalidated (a single
    ``save`` overwrites the stored set). Returns the new codes in plaintext, once."""
    hsh = _hasher(hasher)
    codes = TwoFactor.recovery_codes(count)
    user.two_factor_recovery_codes = [hsh.make(code) for code in codes]
    await user.save()
    return codes


# --- login-challenge state machine (Fortify's "confirm the second factor" step) -----------------

#: session key holding the pending user id — read/write by begin/pending/complete below.
SESSION_PENDING_KEY = "auth.2fa.pending"


class TwoFactorRequired(Exception):
    """Raised by :func:`begin_two_factor_challenge` to signal the login flow must pause for a second
    factor instead of completing a full login. Carries the pending user id (also stashed in the
    session — see :func:`pending_two_factor_user_id`)."""

    def __init__(self, user_id: Any) -> None:
        self.user_id = user_id
        super().__init__(f"two-factor challenge pending for user {user_id!r}")


def requires_two_factor_challenge(user: Any) -> bool:
    """Whether ``user`` must pause at a 2FA challenge before completing login — true once 2FA is
    **confirmed** (``two_factor_confirmed_at`` set); an enabled-but-unconfirmed enrollment does not
    gate login."""
    return getattr(user, "two_factor_confirmed_at", None) is not None


def begin_two_factor_challenge(request: Any, user: Any) -> None:
    """The guard hook: call this from your login flow **instead of** establishing a full login (e.g.
    ``SessionGuard.login``) when :func:`requires_two_factor_challenge` is true. Stashes the pending
    user id under the session key ``auth.2fa.pending`` and raises :class:`TwoFactorRequired` — catch
    it in your login handler to redirect to your app-side ``/two-factor-challenge`` route.
    """
    user_id = (
        user.get_auth_identifier()
        if hasattr(user, "get_auth_identifier")
        else getattr(user, "id", None)
    )
    session = getattr(request, "session", None)
    if isinstance(session, dict):
        session[SESSION_PENDING_KEY] = user_id
    raise TwoFactorRequired(user_id)


def pending_two_factor_user_id(request: Any) -> Any:
    """The user id awaiting a second factor for this request's session, or ``None`` when there's no
    pending challenge — the read-half of :func:`begin_two_factor_challenge`."""
    session = getattr(request, "session", None)
    if not isinstance(session, dict):
        return None
    return cast("dict[str, Any]", session).get(SESSION_PENDING_KEY)


async def complete_two_factor_challenge(
    request: Any, user: Any, code: str, *, hasher: Any = None
) -> bool:
    """Verify ``code`` (TOTP or recovery) against the pending ``user`` and, on success, clear the
    session's pending flag. The caller then completes the *real* login (e.g.
    ``SessionGuard.login(user, request)``); on a failed ``code`` the pending flag is left untouched
    so the challenge can be retried.

    The security-critical first-factor bind is enforced HERE, not delegated to app wiring: the
    passed ``user`` must be the one the session is actually awaiting (``pending_two_factor_user_id``)
    — otherwise a caller who loads ``user`` from a request param could sidestep first-factor auth."""
    pending = pending_two_factor_user_id(request)
    subject = user.get_auth_identifier() if hasattr(user, "get_auth_identifier") else user.id
    if pending is None or pending != subject:
        return False
    if not await verify_two_factor(user, code, hasher=hasher):
        return False
    session = getattr(request, "session", None)
    if isinstance(session, dict):
        cast("dict[str, Any]", session).pop(SESSION_PENDING_KEY, None)
    return True
