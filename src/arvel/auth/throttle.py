"""arvel.auth.throttle — login rate-limiting / lockout.

Brute-force defence for credential login: after ``max_attempts`` failures within ``decay_seconds``
for a given identifier, further attempts are locked out until the window elapses. State is counted
over a ``CacheRepository`` so the limit is shared across processes/hosts. Record a failure on each
bad login; clear the counter on success.

Wire it into ``AuthManager(app, limiter=LoginRateLimiter(cache))`` — it's an opt-in collaborator, so
the default ``AuthManager`` behaviour is unchanged.

**Identifier normalisation:** the bucket key is normalised (``strip().casefold()``) so casing/
whitespace variants of the same login (``Ada@x`` / ``ada@x``) share one bucket — keep this matched
to your user-store lookup. **Cache-outage posture (DR-0015):** if the cache backend errors, the
limiter degrades per ``fail_open`` — default ``True`` (availability: an outage doesn't lock everyone
out; brute-force protection is temporarily absent, so alert on cache unavailability). Set
``fail_open=False`` to fail closed (deny while the cache is down). Grounded in the A&A hardening
backlog (G3) + DR-0015.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any


class LoginRateLimiter:
    """Track + cap failed logins per identifier over a cache backend."""

    def __init__(
        self,
        cache: Any,
        *,
        max_attempts: int | None = None,
        decay_seconds: int | None = None,
        prefix: str = "login",
        fail_open: bool | None = None,
    ) -> None:
        from arvel.kernel.config import config_default

        self._cache = cache
        # Precedence: explicit arg > auth.lockout.* config > built-in default.
        self.max_attempts = (
            max_attempts
            if max_attempts is not None
            else config_default("auth.lockout.max_attempts", 5)
        )
        self.decay_seconds = (
            decay_seconds
            if decay_seconds is not None
            else config_default("auth.lockout.decay_seconds", 900)
        )
        self._prefix = prefix
        self._fail_open = (
            fail_open if fail_open is not None else config_default("auth.lockout.fail_open", True)
        )

    def _norm(self, identifier: str) -> str:
        return identifier.strip().casefold()

    def _key(self, identifier: str) -> str:
        return f"{self._prefix}:{self._norm(identifier)}"

    def _until_key(self, identifier: str) -> str:
        return f"{self._prefix}:{self._norm(identifier)}:until"

    async def too_many_attempts(self, identifier: str) -> bool:
        """Whether ``identifier`` has hit the failure cap (read-only — does not count a hit).

        On a cache error: returns ``False`` when ``fail_open`` (allow), else ``True`` (deny).
        """
        try:
            hits = await self._cache.get(self._key(identifier), 0)
        except Exception:
            return not self._fail_open
        return int(hits or 0) >= self.max_attempts

    async def record_failure(self, identifier: str) -> int:
        """Count one failed attempt and (re)open the decay window. Returns the count (0 on error)."""
        try:
            key = self._key(identifier)
            count = int(await self._cache.increment(key))
            # re-set the TTL on every failure so a missed first-hit can never strand a no-TTL key
            await self._cache.expire(key, self.decay_seconds)
            await self._cache.put(
                self._until_key(identifier),
                int(time.time()) + self.decay_seconds,
                self.decay_seconds,
            )
            if count == self.max_attempts:  # the failure that trips the lockout — log it once
                from arvel.auth.audit import audit

                audit("auth.login.locked_out", level="warning", identifier=self._norm(identifier))
            return count
        except Exception:
            return 0  # best-effort: a cache error must not break the login flow

    async def clear(self, identifier: str) -> None:
        """Reset the counter (call on a successful login)."""
        with contextlib.suppress(Exception):  # best-effort: a cache error must not break login
            await self._cache.forget(self._key(identifier))
            await self._cache.forget(self._until_key(identifier))

    async def available_in(self, identifier: str) -> int:
        """Seconds until the lockout for ``identifier`` lifts (``0`` if not locked / on error)."""
        try:
            until = await self._cache.get(self._until_key(identifier))
        except Exception:
            return 0
        return max(0, int(until) - int(time.time())) if until else 0


__all__ = ["LoginRateLimiter"]
