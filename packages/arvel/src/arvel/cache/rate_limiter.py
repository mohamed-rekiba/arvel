"""RateLimiter — sliding-window rate limiter backed by any CacheStore."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.cache.store import CacheStore


class RateLimiter:
    """Attempt-based rate limiter using the cache backend.

    Uses a simple counter key with a TTL. Compatible with Laravel's
    ``RateLimiter`` mental model.
    """

    def __init__(self, store: CacheStore) -> None:
        self._store = store

    def _counter_key(self, key: str) -> str:
        return f"rate_limiter:{key}"

    async def attempt(self, key: str, max_attempts: int, decay: int) -> bool:
        """Increment the counter and return True if under the limit.

        ``decay`` is the window in seconds. The counter resets after ``decay``
        seconds from the first hit within the window.
        """
        counter_key = self._counter_key(key)
        count = await self._store.get(counter_key)
        if count is None:
            await self._store.put(counter_key, 1, ttl=decay)
            return True
        if int(count) >= max_attempts:
            return False
        await self._store.put(counter_key, int(count) + 1, ttl=decay)
        return True

    async def remaining(self, key: str, max_attempts: int) -> int:
        """Return how many attempts are left in the current window."""
        count = await self._store.get(self._counter_key(key))
        if count is None:
            return max_attempts
        used = int(count)
        return max(0, max_attempts - used)

    async def reset(self, key: str) -> None:
        """Clear the rate limit counter for a key."""
        await self._store.forget(self._counter_key(key))


__all__ = ["RateLimiter"]
