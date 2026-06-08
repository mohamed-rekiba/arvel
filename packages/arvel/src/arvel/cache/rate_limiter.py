"""RateLimiter — fixed-window rate limiter backed by any CacheStore.

The window is anchored to the first hit and does not slide: subsequent hits
increment the counter but keep the original expiry, matching Laravel's
``RateLimiter``. Not single-flight — the read-modify-write isn't atomic, so for
distributed, race-free limiting use the ``Throttle`` middleware (Redis ``INCR``).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from arvel.cache.store import CacheStore


def _window(record: object, now: float) -> tuple[int, float] | None:
    """Return (hits, reset_at) for a live window, or None if absent/expired."""
    if not isinstance(record, dict):
        return None
    data = cast("dict[str, object]", record)
    reset_raw = data.get("reset_at", 0.0)
    reset_at = float(reset_raw) if isinstance(reset_raw, (int, float)) else 0.0
    if now >= reset_at:
        return None
    hits_raw = data.get("hits", 0)
    hits = int(hits_raw) if isinstance(hits_raw, (int, float)) else 0
    return hits, reset_at


class RateLimiter:
    """Attempt-based fixed-window rate limiter using the cache backend."""

    def __init__(self, store: CacheStore) -> None:
        self._store = store

    def _counter_key(self, key: str) -> str:
        return f"rate_limiter:{key}"

    async def attempt(self, key: str, max_attempts: int, decay: int) -> bool:
        """Count one hit; return True if still under ``max_attempts``.

        ``decay`` is the window in seconds, measured from the first hit. Hits
        within the window don't extend it.
        """
        counter_key = self._counter_key(key)
        now = time.time()
        window = _window(await self._store.get(counter_key), now)
        if window is None:
            await self._store.put(counter_key, {"hits": 1, "reset_at": now + decay}, ttl=decay)
            return True
        hits, reset_at = window
        if hits >= max_attempts:
            return False
        # Preserve the original window: only the remaining TTL, never a fresh decay.
        remaining_ttl = max(int(reset_at - now), 1)
        await self._store.put(
            counter_key, {"hits": hits + 1, "reset_at": reset_at}, ttl=remaining_ttl
        )
        return True

    async def remaining(self, key: str, max_attempts: int) -> int:
        """Return how many attempts are left in the current window."""
        window = _window(await self._store.get(self._counter_key(key)), time.time())
        if window is None:
            return max_attempts
        hits, _ = window
        return max(0, max_attempts - hits)

    async def reset(self, key: str) -> None:
        """Clear the rate limit counter for a key."""
        await self._store.forget(self._counter_key(key))


__all__ = ["RateLimiter"]
