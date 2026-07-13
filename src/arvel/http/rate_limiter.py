"""arvel.http.rate_limiter — named, cache-backed rate limiters.

``Limit`` is the declarative rule (attempts per window, optionally segmented and with a custom
429 builder); ``RateLimiter`` registers named limiters (``for_``) and exposes the low-level
counting verbs the ``throttle:<name>`` route middleware (``arvel.http.middleware.ThrottleRequests``)
drives. Counting is **fixed-window** over the app's own cache: ``increment`` bumps the counter,
``expire`` arms its decay on the first hit in a window (story 06's cache verbs — no counting
reimplemented here). the own limiter is fixed-window too (a burst can straddle two windows),
so this isn't a shortcut, just the same trade-off, documented (see docs/middleware.md).

Grounded in knowledge/port/13-http-parity.md §1.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, Literal

Period = Literal["second", "minute", "hour", "day"]

_SECONDS: dict[Period, int] = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


class Limit:
    """A rate limit rule: ``max_attempts`` per ``decay_seconds``, optionally segmented
    (:meth:`by`) and with a custom 429 response builder (:meth:`response`)."""

    def __init__(self, max_attempts: int, decay_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.decay_seconds = decay_seconds
        self.key: str | None = None
        self.response_callback: Callable[[Any], Any] | None = None

    @classmethod
    def per_second(cls, max_attempts: int) -> Limit:
        return cls(max_attempts, _SECONDS["second"])

    @classmethod
    def per_minute(cls, max_attempts: int) -> Limit:
        return cls(max_attempts, _SECONDS["minute"])

    @classmethod
    def per_hour(cls, max_attempts: int) -> Limit:
        return cls(max_attempts, _SECONDS["hour"])

    @classmethod
    def per_day(cls, max_attempts: int) -> Limit:
        return cls(max_attempts, _SECONDS["day"])

    def by(self, key: str) -> Limit:
        """Segment this limit's counter by ``key`` (e.g. per-user, per-tenant, per-route) instead
        of the middleware's default (authenticated user id, else client IP)."""
        self.key = key
        return self

    def response(self, callback: Callable[[Any], Any]) -> Limit:
        """A custom 429 builder: ``callback(request)`` returns the response to send instead of the
        default JSON 429 (a plain dict/``Response`` — whatever a route handler may return)."""
        self.response_callback = callback
        return self


class RateLimiter:
    """Named rate limiters over the app's cache.

    :meth:`for_` registers a named limiter's rule, resolved per-request by the
    ``throttle:<name>`` route middleware. The rest are the low-level counting verbs (usable
    directly, e.g. for login-lockout — see ``arvel.auth.throttle``): they take a caller-chosen
    ``key`` and don't require a registered limiter.
    """

    def __init__(self, cache: Any) -> None:
        self._cache = cache
        self._limiters: dict[str, Callable[[Any], Any]] = {}

    def for_(self, name: str, resolver: Callable[[Any], Any]) -> None:
        """Register ``name``'s rule: ``resolver(request)`` returns a :class:`Limit`, a
        ``list[Limit]`` (all enforced), or ``None`` (unlimited)."""
        self._limiters[name] = resolver

    def limiter(self, name: str) -> Callable[[Any], Any] | None:
        """The resolver registered under ``name`` via :meth:`for_`, or ``None`` if unregistered."""
        return self._limiters.get(name)

    async def attempts(self, key: str) -> int:
        """The current attempt count for ``key`` (0 if unset/expired)."""
        return int(await self._cache.get(key, 0))

    async def hit(self, key: str, decay_seconds: int = 60) -> int:
        """Increment ``key``'s counter, arming its ``decay_seconds`` window on the first hit
        (fixed-window: the counter and its TTL are the same cache entry). Returns the new count."""
        count = await self._cache.increment(key)
        if count == 1:
            await self._cache.expire(key, decay_seconds)
        return int(count)

    async def hit_with_ttl(self, key: str, decay_seconds: int = 60) -> int:
        """Atomic ``hit``: increment-and-arm-the-window in one call via
        :meth:`~arvel.cache.CacheRepository.increment_with_ttl`, so a caller that must decide
        "over limit?" from the returned count (rather than a separate ``attempts`` read first)
        never races a concurrent hit between the check and the increment."""
        count = int(await self._cache.increment_with_ttl(key, 1, decay_seconds))
        if decay_seconds <= 0:
            # cashews reads a non-positive `expire` as no-expiry (same convention
            # `CacheRepository.put`/`.add` special-case), so a zero-length window would otherwise
            # persist forever instead of resetting — evict right after this hit's count is read,
            # so the next call starts fresh (a zero decay window never accumulates).
            await self._cache.forget(key)
        return count

    async def too_many_attempts(self, key: str, max_attempts: int) -> bool:
        """Whether ``key`` has already reached ``max_attempts`` within its current window."""
        return await self.attempts(key) >= max_attempts

    async def attempt(
        self,
        key: str,
        max_attempts: int,
        callback: Callable[[], Any],
        decay_seconds: int = 60,
    ) -> Any:
        """``RateLimiter::attempt``: run+count ``callback`` unless ``key`` is already over
        ``max_attempts`` (then skip it and return ``False``). A ``None`` callback result counts as
        success (``True``); any other result is returned as-is."""
        if await self.too_many_attempts(key, max_attempts):
            return False
        result = callback()
        if inspect.isawaitable(result):
            result = await result
        await self.hit(key, decay_seconds)
        return True if result is None else result

    async def remaining(self, key: str, max_attempts: int) -> int:
        """Attempts left for ``key`` before it hits ``max_attempts`` (never negative)."""
        return max(max_attempts - await self.attempts(key), 0)

    async def available_in(self, key: str) -> int:
        """Seconds until ``key``'s window resets (0 if it's not currently armed)."""
        # `.client` is the repository's public escape hatch to the raw cashews client (used here,
        # not re-implemented, per doc 16) — cashews' own `get_expire` mirrors redis TTL semantics:
        # remaining seconds, -1 (no expiry), or -2 (missing key); the latter two both mean "now".
        ttl = await self._cache.client.get_expire(key)
        return max(int(ttl), 0)

    async def clear(self, key: str) -> None:
        """Reset ``key``'s counter."""
        await self._cache.forget(key)


__all__ = ["Limit", "RateLimiter"]
