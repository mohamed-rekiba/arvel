"""arvel.auth.tokens — personal API tokens: scopes + expiry + last-used + abilities middleware.

A token is a high-entropy random string shown to the client **once**; only its SHA-256 hash is
stored, so a database leak doesn't expose usable tokens. Each token carries **abilities** (scopes —
``["*"]`` grants everything) and an optional **expiry**; ``resolve_token`` rejects expired tokens and
``ApiToken.can(ability)`` checks the scope. ``TokenGuard`` authenticates a request from its
``Authorization: Bearer <token>`` header, and sets :func:`current_access_token` for the rest of the
request (the current-access-token accessor, request-scoped here
instead of hung off the model instance). ``abilities()``/``ability()`` build route-middleware classes
that authenticate the bearer token *and* enforce its scopes in one step — arvel's equivalent of
the named ``abilities:a,b``/``ability:a`` middleware pattern, but built from explicit string args (like
``Authorize()`` in ``arvel.auth.middleware``) rather than parsed from a colon-separated alias string.
Parity glue over stdlib hashing — not a reimplementation of any crypto primitive. Grounded in
knowledge/port/15.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterable
from typing import Any, ClassVar, cast

import sqlalchemy as sa

from arvel.database import Model
from arvel.http.middleware import Middleware

#: the ApiToken active for this request — set by TokenGuard once it resolves a valid bearer token.
#: Backed by the support-layer contextvar so the http kernel resets it per request (like
#: current_user), closing a cross-request token-identity leak.
from arvel.support import access_token as _current_token


class ApiToken(Model):
    """A personal access token bound to a user (``tokenable_id``), with scopes + optional expiry."""

    __table_name__ = "api_tokens"
    __fields__: ClassVar[dict[str, Any]] = {
        "name": str,
        "token": str,
        "tokenable_id": int,
        "abilities": sa.Text(),  # JSON-encoded list of scopes (cast below); TEXT, matches migration
        "expires_at": str,  # datetime cast (below) → a real DateTime column
        "last_used_at": str,  # datetime cast (below); throttled-write, see _touch_last_used
    }
    __fillable__: ClassVar[list[str]] = [
        "name",
        "token",
        "tokenable_id",
        "abilities",
        "expires_at",
    ]
    __casts__: ClassVar[dict[str, str]] = {
        "abilities": "json",
        "expires_at": "datetime",
        "last_used_at": "datetime",
    }

    def can(self, ability: str) -> bool:
        """Whether the token is scoped for ``ability``: ``"*"`` grants everything, else exact match.

        An unset/empty abilities list grants nothing (fail closed).
        """
        # getattr(..., None): a legacy/partial row missing the column degrades to deny, not a crash
        abilities = cast("list[Any]", getattr(self, "abilities", None) or [])
        return "*" in abilities or ability in abilities

    def is_expired(self) -> bool:
        """``True`` when the token has an ``expires_at`` in the past (``None`` never expires)."""
        expires_at = getattr(self, "expires_at", None)  # absent column → treat as non-expiring
        if expires_at is None:
            return False
        from arvel.dates import Date

        return bool(expires_at.to_py() < Date.now().to_py())


def _hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


async def create_token(
    user: Any,
    name: str = "default",
    *,
    abilities: Iterable[str] = ("*",),
    expires_in: int | None = None,
) -> tuple[str, ApiToken]:
    """Issue a token for ``user``; returns ``(plaintext, record)`` — show the plaintext once.

    ``abilities`` scopes the token (default ``["*"]`` = all). ``expires_in`` is a lifetime in
    **seconds**; omit (``None``) to fall back to the global default expiration, config
    ``api_tokens.expiration`` (**minutes**) — or a non-expiring token when that's unset
    too (the default: ``None``).

    Validated at mint (fail fast, never store a footgun token): a bare ``str`` ability is treated as a
    single ability (not split into characters); ``abilities`` must be a non-empty iterable of
    non-empty strings; ``expires_in`` (when given) must be a positive integer of seconds.
    """
    if isinstance(abilities, str):
        abilities = [abilities]  # DWIM: one ability string → one-element list, not char-split
    # list[Any] so the runtime type checks below are meaningful even for untyped callers.
    ability_list: list[Any] = list(abilities)
    if not ability_list or any(not isinstance(a, str) or not a.strip() for a in ability_list):
        raise ValueError(
            "create_token: abilities must be a non-empty iterable of non-empty strings"
        )
    # bool is an int subclass — reject it explicitly (expires_in=True must not mean "1 second").
    if expires_in is not None and (isinstance(expires_in, bool) or expires_in <= 0):
        raise ValueError("create_token: expires_in must be a positive integer (seconds), or None")

    resolved_expires_in = expires_in
    if resolved_expires_in is None:
        from arvel.kernel.config import config_default

        default_minutes = config_default("api_tokens.expiration", None)
        if default_minutes is not None:
            resolved_expires_in = int(default_minutes) * 60

    plaintext = secrets.token_hex(32)
    expires_at = None
    if resolved_expires_in is not None:
        from arvel.dates import Date

        expires_at = Date.now().add(seconds=resolved_expires_in)
    record = await ApiToken.create(
        name=name,
        token=_hash(plaintext),
        tokenable_id=user.id,
        abilities=ability_list,
        expires_at=expires_at,
    )
    return plaintext, record


async def prune_expired_tokens() -> int:
    """Delete every expired API token; returns the count removed. Non-expiring tokens are kept.

    Decided by the same instant-domain rule as ``resolve_token`` (``ApiToken.is_expired``), so a token
    is pruned only once it would already be rejected — timezone- and ISO-format-independent (a DB-side
    string comparison of ``expires_at`` can misorder across a DST offset change). Expired tokens are
    already inert; this reclaims rows. Scans the table — run it as a periodic job; index ``expires_at``
    and/or batch if the table grows large.
    """
    expired = [token.id for token in await ApiToken.get() if token.is_expired()]
    if not expired:
        return 0
    await ApiToken.where_in("id", expired).delete()
    return len(expired)


async def resolve_token(plaintext: str) -> ApiToken | None:
    """Find a **valid** (existing + non-expired) token record for a plaintext token, or ``None`` —
    and (throttled) stamp its ``last_used_at``."""
    record: ApiToken | None = await ApiToken.where(token=_hash(plaintext)).first()
    if record is None or record.is_expired():
        return None
    await _touch_last_used(record)
    return record


async def _touch_last_used(record: ApiToken) -> None:
    """Stamp ``last_used_at`` — throttled to at most once per config ``api_tokens.last_used_throttle``
    seconds (default 60), so a hot endpoint doesn't take a write on every single request.
    The reference behavior stamps ``last_used_at`` unconditionally each request; this throttle is an idiomatic,
    documented divergence (see docs/auth/api-tokens.md)."""
    from arvel.dates import Date
    from arvel.kernel.config import config_default

    throttle = int(config_default("api_tokens.last_used_throttle", 60))
    last_used_at = getattr(record, "last_used_at", None)
    now = Date.now()
    if last_used_at is not None and (now.to_py() - last_used_at.to_py()).total_seconds() < throttle:
        return
    record.last_used_at = now
    await record.save()


async def revoke_all_tokens(tokenable_id: int) -> None:
    """Delete every API token for a user (revocation — there is no soft-revoke flag)."""
    await ApiToken.where(tokenable_id=tokenable_id).delete()


class TokenGuard:
    """Authenticate a request from its ``Authorization: Bearer <token>`` header."""

    async def token(self, request: Any) -> ApiToken | None:
        """The validated (non-expired) ``ApiToken`` for the request — so callers can check abilities.
        Also sets :func:`current_access_token` for the rest of the request on a successful resolve."""
        header = request.header("authorization") if hasattr(request, "header") else None
        if not header or not header.lower().startswith("bearer "):
            return None
        record = await resolve_token(header[7:].strip())
        if record is not None:
            _current_token.set(record)
        return record

    async def user_id(self, request: Any) -> Any:
        token = await self.token(request)
        return token.tokenable_id if token is not None else None


def current_access_token() -> ApiToken | None:
    """The ``ApiToken`` active for this request — set by :class:`TokenGuard` once it resolves a valid
    bearer token; ``None`` outside a token-authenticated request (the
    ``$request->user()->currentAccessToken()``, request-scoped here instead of hung off the user)."""
    return cast("ApiToken | None", _current_token.get())


def token_can(ability: str) -> bool:
    """Whether :func:`current_access_token` may perform ``ability`` — ``False`` with no active token
    (fail closed)."""
    token = current_access_token()
    return token is not None and token.can(ability)


def abilities(*required: str) -> type[Any]:
    """A route-middleware **class** requiring the active bearer token to hold **all** of
    ``required`` (the ``abilities:a,b`` form). Authenticates the bearer token itself (**401** if
    missing/invalid/expired) and enforces the scope (**403** if any ability is missing) — one
    middleware covers both steps. Returns a class, like ``Authorize()``:
    ``router.get(..., middleware=[abilities("posts.read", "posts.write")])``.
    """

    class _RequireAllAbilities(Middleware):
        required_abilities: ClassVar[tuple[str, ...]] = required

        async def handle(self, request: Any, call_next: Any) -> Any:
            from arvel.http.exceptions import abort

            token = await TokenGuard().token(request)
            if token is None:
                abort(401)
            if not all(token.can(a) for a in required):
                abort(403)
            return await call_next(request)

    _RequireAllAbilities.__name__ = f"abilities({', '.join(required)!r})"
    _RequireAllAbilities.__qualname__ = _RequireAllAbilities.__name__
    return _RequireAllAbilities


def ability(*any_of: str) -> type[Any]:
    """A route-middleware **class** requiring the active bearer token to hold **any** of ``any_of``
    (the ``ability:a`` form). Same 401/403 shape as :func:`abilities`, just OR'd instead of AND'd."""

    class _RequireAnyAbility(Middleware):
        required_abilities: ClassVar[tuple[str, ...]] = any_of

        async def handle(self, request: Any, call_next: Any) -> Any:
            from arvel.http.exceptions import abort

            token = await TokenGuard().token(request)
            if token is None:
                abort(401)
            if not any(token.can(a) for a in any_of):
                abort(403)
            return await call_next(request)

    _RequireAnyAbility.__name__ = f"ability({', '.join(any_of)!r})"
    _RequireAnyAbility.__qualname__ = _RequireAnyAbility.__name__
    return _RequireAnyAbility


__all__ = [
    "ApiToken",
    "TokenGuard",
    "abilities",
    "ability",
    "create_token",
    "current_access_token",
    "prune_expired_tokens",
    "resolve_token",
    "revoke_all_tokens",
    "token_can",
]
