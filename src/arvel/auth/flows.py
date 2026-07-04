"""arvel.auth.flows — email-verification tokens (signed URLs).

A purpose-tagged, time-limited token over ``arvel.security.Signer`` (itsdangerous). The payload binds
a **hash of the email** the link was issued for (``verify:<user_id>:<email_hash>``); ``verify_email_token``
recomputes the hash from the *current* user email and rejects on mismatch, so a link survives neither a
signature forgery nor a since-changed email address. Default TTL is 60 minutes (Laravel parity).

Password reset moved to :mod:`arvel.auth.password_reset` (a stored, single-use, throttled broker — the
old stateless signed token here was replayable within its TTL, audit finding A6). Route handlers (send
link / confirm) are app-side. Grounded in knowledge/port/15 + projects/arvel/specs/14-auth-session.md.
"""

from __future__ import annotations

import hashlib
from typing import Any

DEFAULT_TTL_SECONDS = 3600  # 60 minutes (Laravel default; down from the prior 24h)


def _signer(secret: str) -> Any:
    from arvel.security import Signer

    return Signer(secret)


def _email_hash(email: str) -> str:
    """A stable (non-secret) hash of ``email``, normalized so casing/whitespace variants match the
    same address a user actually has on file."""
    return hashlib.sha256(email.strip().casefold().encode()).hexdigest()


def email_verification_token(user_id: int, email: str, secret: str) -> str:
    """A signed token proving ownership of ``email`` *at issuance time* — the payload binds
    ``sha256(email)`` so :func:`verify_email_token` can reject it once the user's email changes."""
    payload = f"verify:{user_id}:{_email_hash(email)}"
    return str(_signer(secret).sign(payload))


def verify_email_token(
    token: str, current_email: str, secret: str, *, max_age: int = DEFAULT_TTL_SECONDS
) -> int | None:
    """The user id if ``token`` is validly signed, unexpired, and its bound email hash matches
    ``current_email`` — else ``None``. Passing the user's *current* email (not the one at issuance)
    is what invalidates a link after an email change; default ``max_age`` is 60 minutes."""
    try:
        value = _signer(secret).unsign(token, max_age=max_age)
    except Exception:
        return None
    parts = str(value).split(":", 2)
    if len(parts) != 3 or parts[0] != "verify" or not parts[1].isdigit():
        return None
    if parts[2] != _email_hash(current_email):
        return None
    return int(parts[1])
