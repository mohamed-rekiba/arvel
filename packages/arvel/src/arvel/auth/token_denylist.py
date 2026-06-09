"""Revocation denylist for stateless access JWTs.

A signed JWT is valid until ``exp`` — there's no way to take it back without
server-side state. This module is that state, backed by the Cache subsystem
(shared across workers when a Redis cache is configured).

Two mechanisms:

- **Per-``jti`` deny** — kill one token (single-session logout) until it would
  have expired anyway. Self-cleans via the cache TTL.
- **Per-user cutoff** — kill every token issued before a moment in time
  (password reset, refresh-token-reuse detection, "log out everywhere"). A token
  is rejected when its ``iat`` predates the cutoff.

Checks **fail open**: if the cache is unavailable the token is treated as *not*
revoked, so a cache outage degrades to "revocation stops working" rather than
"every request is rejected". That's the standard JWT-denylist tradeoff.
"""

from __future__ import annotations

import time

from arvel.cache.exceptions import CacheException
from arvel.facades.cache import Cache
from arvel.logging.facade import Log

_DENY_PREFIX = "auth:jwt:denied:"
_REVOKE_PREFIX = "auth:jwt:revoked_before:"


async def deny_token(jti: str, *, expires_at_epoch: int) -> None:
    """Deny a single token by ``jti`` until it would have expired on its own."""
    if not jti:
        return
    ttl = max(expires_at_epoch - int(time.time()), 1)
    try:
        await Cache.put(f"{_DENY_PREFIX}{jti}", "1", ttl=ttl)
    except CacheException:
        Log.warning("auth.denylist.unavailable", op="deny_token")


async def is_token_denied(jti: str) -> bool:
    """True when ``jti`` was explicitly denied. Fails open (False) on cache error."""
    if not jti:
        return False
    try:
        return await Cache.has(f"{_DENY_PREFIX}{jti}")
    except CacheException:
        return False


async def revoke_all_for_user(user_id: str, *, ttl_seconds: int) -> None:
    """Revoke every access token for ``user_id`` issued before now.

    ``ttl_seconds`` should be at least the access-token lifetime — once every
    pre-cutoff token has expired the marker is no longer needed and self-cleans.
    """
    if not user_id:
        return
    key = f"{_REVOKE_PREFIX}{user_id}"
    try:
        await Cache.put(key, str(int(time.time())), ttl=max(ttl_seconds, 1))
    except CacheException:
        Log.warning("auth.denylist.unavailable", op="revoke_all_for_user")


async def revoked_before_for_user(user_id: str) -> int | None:
    """The cutoff epoch for ``user_id``, or None. Fails open (None) on cache error."""
    if not user_id:
        return None
    try:
        raw = await Cache.get(f"{_REVOKE_PREFIX}{user_id}")
    except CacheException:
        return None
    if raw is None:
        return None
    try:
        return int(raw)
    except TypeError, ValueError:
        return None


async def is_revoked(*, jti: str, subject: str, issued_at: int | None) -> bool:
    """True when a token is revoked — denied by ``jti`` or before the user cutoff.

    A token with no ``iat`` is treated as revoked once the user has a cutoff set:
    the user asked to kill their sessions, so a token we can't date doesn't get
    the benefit of the doubt.
    """
    if await is_token_denied(jti):
        return True
    cutoff = await revoked_before_for_user(subject)
    if cutoff is None:
        return False
    return issued_at is None or issued_at < cutoff


__all__ = [
    "deny_token",
    "is_revoked",
    "is_token_denied",
    "revoke_all_for_user",
    "revoked_before_for_user",
]
