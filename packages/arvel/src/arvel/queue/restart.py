"""Queue restart signal (WI-arvel-023, ADR-073).

Writes a UTC timestamp to a cache key the worker polls once per loop. Workers
compare the timestamp against their own ``started_at`` and exit gracefully
when the marker is newer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.cache.store import CacheStore

_CACHE_KEY = "arvel:queue:restart"


class QueueRestartSignal:
    """Reads and writes the queue-restart cache marker.

    The implementation defers to the cache facade so the same surface works
    against any registered cache store (in-memory, Redis, file).
    """

    def __init__(self, cache_key: str = _CACHE_KEY) -> None:
        self._cache_key: str = cache_key

    @property
    def cache_key(self) -> str:
        return self._cache_key

    async def signal_restart(self) -> datetime:
        """Write the current UTC time to the cache and return it."""
        now = datetime.now(UTC)
        store = self._resolve_store()
        if store is not None:
            await store.put(self._cache_key, now.isoformat())
        return now

    async def last_restart(self) -> datetime | None:
        """Return the timestamp of the last restart signal, or None if absent."""
        store = self._resolve_store()
        if store is None:
            return None
        raw = await store.get(self._cache_key)
        if not isinstance(raw, str) or not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    @staticmethod
    def _resolve_store() -> CacheStore | None:
        from arvel.cache.exceptions import FacadeNotBoundError
        from arvel.facades.cache import Cache

        try:
            return Cache.store(None)
        except FacadeNotBoundError:
            return None
