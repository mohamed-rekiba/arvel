"""arvel.auth.remember — persistent login ("remember me") via the selector/validator pattern.

A remember cookie keeps a user logged in across browser sessions. The cookie carries
``selector:validator``: the **selector** is a random public handle used for an indexed, single-row
lookup (so no token is leaked by timing the lookup), and the **validator** is a high-entropy secret
of which only a SHA-256 **hash** is stored. On each use the validator is **rotated** (single-use), so
a stolen-then-replayed cookie no longer matches → the row is deleted (theft-evident). Storing only
the hash means a database leak can't be replayed. Recall is a privilege grant, so it rotates the
session id (fixation defence). Mirrors ``arvel.auth.refresh``; grounded in the A&A hardening backlog
(G5) and knowledge/port/15.

Accepted tradeoff (standard for selector/validator): the selector is the public half of the cookie,
so anyone who learns it (e.g. via leaked request/proxy logs) can force-delete that one token — a
nuisance forced-logout, not account takeover. Keep the ``remember`` cookie out of logs and treat the
``remember_tokens`` table at session-material data class.
"""

from __future__ import annotations

import hashlib
import inspect
import secrets
from typing import Any, ClassVar

from arvel.database import Model
from arvel.http.middleware import Middleware
from arvel.http.session import regenerate_session

REMEMBER_COOKIE = "remember"
DEFAULT_TTL = 60 * 60 * 24 * 30  # 30 days


class RememberToken(Model):
    """A persistent-login token bound to a user. Only the validator **hash** is stored."""

    __table_name__ = "remember_tokens"
    __fields__: ClassVar[dict[str, Any]] = {
        "selector": str,
        "validator": str,  # SHA-256 hash of the validator secret
        "tokenable_id": int,
        "expires_at": str,  # ISO datetime (cast below)
    }
    __fillable__: ClassVar[list[str]] = ["selector", "validator", "tokenable_id", "expires_at"]
    __casts__: ClassVar[dict[str, str]] = {"expires_at": "datetime"}


def _hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _parse(cookie: str) -> tuple[str, str] | None:
    selector, _, validator = cookie.partition(":")
    if not selector or not validator:
        return None
    return selector, validator


# --- token store --------------------------------------------------------------


async def issue_remember_token(tokenable_id: int, *, ttl: int | None = None) -> str:
    """Issue a remember token for a user; returns the ``selector:validator`` cookie value.

    ``ttl`` defaults to ``auth.remember.ttl`` (else ``DEFAULT_TTL``) when omitted.
    """
    from arvel.dates import Date
    from arvel.kernel.config import config_default

    seconds: int = ttl if ttl is not None else config_default("auth.remember.ttl", DEFAULT_TTL)
    selector = secrets.token_hex(16)
    validator = secrets.token_hex(32)
    await RememberToken.create(
        selector=selector,
        validator=_hash(validator),
        tokenable_id=tokenable_id,
        expires_at=Date.now().add(seconds=seconds),
    )
    return f"{selector}:{validator}"


async def recall_remember_token(cookie: str) -> tuple[int, str] | None:
    """Validate a remember cookie and, on success, **rotate** it.

    Returns ``(tokenable_id, new_cookie_value)`` — the caller re-sets the rotated cookie. Returns
    ``None`` (fail closed) for a malformed, unknown, expired, or forged cookie. A selector hit whose
    validator doesn't match is treated as theft/forgery: that row is deleted.
    """
    from arvel.dates import Date

    parsed = _parse(cookie)
    if parsed is None:
        return None
    selector, validator = parsed
    row = await RememberToken.where(selector=selector).first()
    if row is None:
        return None
    if row.expires_at is not None and row.expires_at.to_py() < Date.now().to_py():
        await row.delete()  # expired → clean up
        return None
    if not secrets.compare_digest(str(row.validator), _hash(validator)):
        from arvel.auth.audit import audit

        await row.delete()  # validator mismatch on a known selector → theft/forgery, kill it
        audit(
            "auth.remember.theft_detected",
            level="warning",
            selector=selector,
            tokenable_id=row.tokenable_id,
        )
        return None
    # Rotate atomically: WHERE selector = ? AND validator = <current hash>. Of two concurrent
    # requests presenting the same cookie exactly one flips the validator (rowcount == 1); the other
    # matches zero rows and bows out, so a single valid successor is minted — no last-write-wins race
    # that would strand one client with a stale cookie.
    new_validator = secrets.token_hex(32)
    claimed = await RememberToken.where(selector=selector, validator=str(row.validator)).update(
        {"validator": _hash(new_validator)}
    )
    if getattr(claimed, "rowcount", 0) < 1:
        return None  # a concurrent request already rotated this token
    return row.tokenable_id, f"{selector}:{new_validator}"


async def clear_remember_token(cookie: str) -> None:
    """Delete the token behind a remember cookie (logout). No-op for a malformed cookie."""
    parsed = _parse(cookie)
    if parsed is None:
        return
    row = await RememberToken.where(selector=parsed[0]).first()
    if row is not None:
        await row.delete()


async def clear_all_remember_tokens(tokenable_id: object) -> None:
    """Delete every remember token for a user (e.g. password change / log out everywhere)."""
    await RememberToken.where(tokenable_id=tokenable_id).delete()


# --- HTTP glue ----------------------------------------------------------------


async def remember(request: Any, user: Any, *, ttl: int | None = None) -> None:
    """Issue a remember token for ``user`` and flag the cookie to be set (call on login).

    ``ttl`` defaults to ``auth.remember.ttl`` (else ``DEFAULT_TTL``) when omitted.
    """
    identifier = user.get_auth_identifier() if hasattr(user, "get_auth_identifier") else user.id
    request._remember_set = await issue_remember_token(int(identifier), ttl=ttl)


async def forget_remember(request: Any) -> None:
    """Delete the remember token (if any) and flag the cookie to be cleared (call on logout)."""
    getter = getattr(request, "cookie", None)
    cookie = getter(REMEMBER_COOKIE) if callable(getter) else None
    if cookie:
        await clear_remember_token(str(cookie))
    request._remember_clear = True


class RememberMe(Middleware):
    """Recall a logged-out user from their remember cookie (place **after** AuthenticateMiddleware).

    When no user is already authenticated and a valid remember cookie is present, it logs the user in
    for the request, rotates the cookie, and seeds the session (``session_key``) so subsequent
    requests authenticate from the session instead of re-recalling. An invalid/forged cookie is
    cleared. ``user_loader(id)`` resolves the user model (may be sync or async).
    """

    def __init__(
        self,
        user_loader: Any,
        *,
        cookie: str = REMEMBER_COOKIE,
        secure: bool | None = None,
        ttl: int | None = None,
        session_key: str = "_user_id",
    ) -> None:
        from arvel.kernel.config import config_default

        self._load_user = user_loader
        self._cookie = cookie
        # Precedence: explicit arg > auth.remember.* config > built-in default.
        self._secure = (
            secure if secure is not None else config_default("auth.remember.secure", True)
        )
        self._ttl = ttl if ttl is not None else config_default("auth.remember.ttl", DEFAULT_TTL)
        self._session_key = session_key

    async def handle(self, request: Any, call_next: Any) -> Any:
        from arvel.auth import current_user

        getter = getattr(request, "cookie", None)
        cookie = getter(self._cookie) if callable(getter) else None
        if (
            current_user.get() is not None  # already authenticated (e.g. session) — leave it
            or getattr(request, "_remember_clear", False)
            or not cookie
        ):
            return await call_next(request)

        result = await recall_remember_token(str(cookie))
        if result is None:
            request._remember_clear = True  # stale/forged → clear the cookie
            return await call_next(request)
        tokenable_id, rotated = result
        loaded = self._load_user(tokenable_id)
        user = await loaded if inspect.isawaitable(loaded) else loaded
        if user is None:
            request._remember_clear = True
            return await call_next(request)

        request._remember_set = rotated  # re-set the rotated cookie
        regenerate_session(
            request
        )  # recall is a privilege grant (anon→authed) → rotate id (fixation)
        session = getattr(request, "session", None)
        if isinstance(session, dict):
            session[self._session_key] = tokenable_id  # persist so we don't recall every request
            # so this recalled session participates in "log out other devices" eviction too
            from arvel.auth.sessions import stamp_session

            await stamp_session(session, tokenable_id)
        token = current_user.set(user)
        try:
            return await call_next(request)
        finally:
            current_user.reset(token)

    async def terminate(self, request: Any, response: Any) -> None:
        if getattr(request, "_remember_clear", False):
            deleter = getattr(response, "delete_cookie", None)
            if callable(deleter):
                deleter(self._cookie, path="/")
            return
        value = getattr(request, "_remember_set", None)
        if value:
            setter = getattr(response, "set_cookie", None)
            if callable(setter):
                setter(
                    self._cookie,
                    value,
                    max_age=self._ttl,
                    path="/",
                    httponly=True,
                    secure=self._secure,
                    samesite="lax",
                )


__all__ = [
    "DEFAULT_TTL",
    "REMEMBER_COOKIE",
    "RememberMe",
    "RememberToken",
    "clear_all_remember_tokens",
    "clear_remember_token",
    "forget_remember",
    "issue_remember_token",
    "recall_remember_token",
    "remember",
]
