"""arvel.auth.tokens — API tokens (Sanctum parity): scopes + expiry.

A token is a high-entropy random string shown to the client **once**; only its SHA-256 hash is
stored, so a database leak doesn't expose usable tokens. Each token carries **abilities** (scopes —
``["*"]`` grants everything) and an optional **expiry**; ``resolve_token`` rejects expired tokens and
``ApiToken.can(ability)`` checks the scope. ``TokenGuard`` authenticates a request from its
``Authorization: Bearer <token>`` header. Parity glue over stdlib hashing — not a reimplementation of
any crypto primitive. Grounded in knowledge/port/15.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterable
from typing import Any, ClassVar, cast

import sqlalchemy as sa

from arvel.database import Model


class ApiToken(Model):
    """A personal access token bound to a user (``tokenable_id``), with scopes + optional expiry."""

    __table_name__ = "api_tokens"
    __fields__: ClassVar[dict[str, Any]] = {
        "name": str,
        "token": str,
        "tokenable_id": int,
        "abilities": sa.Text(),  # JSON-encoded list of scopes (cast below); TEXT, matches migration
        "expires_at": str,  # datetime cast (below) → a real DateTime column (DR-0023)
    }
    __fillable__: ClassVar[list[str]] = [
        "name",
        "token",
        "tokenable_id",
        "abilities",
        "expires_at",
    ]
    __casts__: ClassVar[dict[str, str]] = {"abilities": "json", "expires_at": "datetime"}

    def can(self, ability: str) -> bool:
        """Whether the token is scoped for ``ability``: ``"*"`` grants everything, else exact match.

        An unset/empty abilities list grants nothing (fail closed).
        """
        # getattr(..., None) so a legacy/partial row missing the column degrades to deny (the model's
        # __getattr__ raises on an absent column) — fail closed, not crash.
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
    **seconds**; omit (``None``) for a non-expiring token.

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

    plaintext = secrets.token_hex(32)
    expires_at = None
    if expires_in is not None:
        from arvel.dates import Date

        expires_at = Date.now().add(seconds=expires_in)
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
    """Find a **valid** (existing + non-expired) token record for a plaintext token, or ``None``."""
    record: ApiToken | None = await ApiToken.where(token=_hash(plaintext)).first()
    if record is None or record.is_expired():
        return None
    return record


async def revoke_all_tokens(tokenable_id: int) -> None:
    """Delete every API token for a user (revocation — there is no soft-revoke flag)."""
    await ApiToken.where(tokenable_id=tokenable_id).delete()


class TokenGuard:
    """Authenticate a request from its ``Authorization: Bearer <token>`` header."""

    async def token(self, request: Any) -> ApiToken | None:
        """The validated (non-expired) ``ApiToken`` for the request — so callers can check abilities."""
        header = request.header("authorization") if hasattr(request, "header") else None
        if not header or not header.lower().startswith("bearer "):
            return None
        return await resolve_token(header[7:].strip())

    async def user_id(self, request: Any) -> Any:
        token = await self.token(request)
        return token.tokenable_id if token is not None else None
