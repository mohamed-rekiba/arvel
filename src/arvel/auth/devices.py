"""arvel.auth.devices — sign out of all devices (credential revocation).

"Log out everywhere" revokes every **persistent** credential a user holds so no device can silently
re-authenticate: rotating refresh tokens, remember-me tokens, and personal API tokens. Use it on a
password change, on a credential-compromise response, or behind a "sign out of all devices" button —
then have the current device log in again.

Honest scope note: arvel's web *sessions* are keyed by an opaque cookie with no user index
(``StartSession``), so active web sessions on other devices cannot be individually enumerated or killed
today — they simply lapse at the session lifetime (default 2h). Instant "keep this device, drop the
others" for *live* sessions needs a per-user session registry (a follow-up). What this module
guarantees now is the security-meaningful boundary: the long-lived credentials that let a device come
back are all revoked. For the current device, pair with ``invalidate_session`` (logout here) as needed.
Grounded in the A&A hardening backlog (G8).
"""

from __future__ import annotations

from typing import Any

from arvel.auth.refresh import revoke_all_refresh_tokens
from arvel.auth.remember import clear_all_remember_tokens
from arvel.auth.tokens import revoke_all_tokens


def _ident(user: Any) -> int:
    getter = getattr(user, "get_auth_identifier", None)
    raw: Any = getter() if callable(getter) else getattr(user, "id", None)
    if raw is None:
        raise ValueError("cannot revoke credentials for an unidentified user")
    return int(raw)


async def logout_everywhere(user: Any) -> None:
    """Revoke all of ``user``'s persistent credentials — refresh + remember + API tokens.

    After this no device can silently re-authenticate. Call on password change / compromise / a
    "sign out of all devices" action (then re-login the current device). It also bumps the session
    generation, so **live web sessions are evicted too** wherever ``EnsureSessionCurrent`` is wired
    (otherwise they lapse at the session TTL).

    **Best-effort and loud:** every store is attempted even if one fails, and an
    :class:`ExceptionGroup` is raised if any did — a security event must never half-complete
    *silently* (a caller seeing success must be able to trust it). The highest-impact credential
    (long-lived, ``*``-scoped API tokens) is revoked first.
    """
    from arvel.auth.audit import audit
    from arvel.auth.sessions import invalidate_all_sessions

    tokenable_id = _ident(user)
    errors: list[Exception] = []
    for revoke in (revoke_all_tokens, revoke_all_refresh_tokens, clear_all_remember_tokens):
        try:
            await revoke(tokenable_id)
        except Exception as exc:  # collect + re-raise; never swallow a revocation failure
            errors.append(exc)
    # Also bump the session generation so LIVE web sessions are evicted (where EnsureSessionCurrent is
    # wired) — best-effort, never raises (a cache miss just means live sessions lapse at TTL instead).
    await invalidate_all_sessions(tokenable_id)
    audit("auth.logout_everywhere", tokenable_id=tokenable_id, failures=len(errors))
    if errors:
        raise ExceptionGroup("logout_everywhere: some credentials were not revoked", errors)
