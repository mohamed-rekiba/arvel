"""arvel.cache — the Cache manager on **cashews** (mandated engine; DR-0002).

``array`` (in-memory) is the core driver; ``redis`` needs the ``[redis]`` extra —
both are real cashews backends (never a stdlib stand-in: G4). The ``CacheRepository``
wraps a ``cashews.Cache`` with Laravel-style ``get``/``put``/``remember``/``forget``/
``lock``. cashews is imported lazily so ``import arvel`` stays light.
Grounded in knowledge/port/16-managers.md.
"""

from __future__ import annotations

import inspect
from typing import Any

from arvel.kernel import Settings
from arvel.support.manager import Manager
from arvel.telemetry import span


class CacheSettings(Settings):
    """Typed, validated view over the ``cache`` config section (DR-0016).

    ``default`` is a driver name (an open registry — packages add drivers — so it stays ``str``);
    ``url`` is the redis DSN for the ``redis`` driver.
    """

    __config_key__ = "cache"
    default: str = "array"
    url: str = "redis://localhost:6379/0"


class CacheRepository:
    """Laravel-style cache API over a configured ``cashews.Cache`` client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def client(self) -> Any:
        return self._client

    async def get(self, key: str, default: Any = None) -> Any:
        with span("cache get", kind="client", attributes={"cache.operation": "get"}) as sp:
            value = await self._client.get(key)
            if sp is not None:
                sp.set_attribute("cache.hit", value is not None)
            return default if value is None else value

    async def put(self, key: str, value: Any, ttl: int | None = None) -> bool:
        with span("cache put", kind="client", attributes={"cache.operation": "put"}):
            await self._client.set(key, value, expire=ttl)
            return True

    async def has(self, key: str) -> bool:
        return await self._client.get(key) is not None

    async def forget(self, key: str) -> bool:
        with span("cache forget", kind="client", attributes={"cache.operation": "forget"}):
            await self._client.delete(key)
            return True

    async def flush(self) -> bool:
        """Remove every entry from the store (Laravel ``Cache::flush`` / ``cache:clear``)."""
        with span("cache flush", kind="client", attributes={"cache.operation": "flush"}):
            await self._client.clear()
            return True

    async def increment(self, key: str, by: int = 1) -> int:
        """Atomically add ``by`` to a counter (created at 0 if absent); returns the new value."""
        with span("cache increment", kind="client", attributes={"cache.operation": "increment"}):
            return int(await self._client.incr(key, by))

    async def expire(self, key: str, ttl: int) -> bool:
        """Set/refresh a key's time-to-live in seconds."""
        await self._client.expire(key, ttl)
        return True

    async def remember(self, key: str, ttl: int | None, callback: Any) -> Any:
        value = await self._client.get(key)
        if value is not None:
            return value
        computed = callback()
        if inspect.isawaitable(computed):
            computed = await computed
        await self._client.set(key, computed, expire=ttl)
        return computed

    async def remember_forever(self, key: str, callback: Any) -> Any:
        return await self.remember(key, None, callback)

    def lock(self, key: str, ttl: int | None = None) -> Any:
        """An atomic lock (async context manager) over the cache backend."""
        return self._client.lock(key, expire=ttl)


class CacheManager(Manager):
    """Resolves cache drivers (cashews backends) by config."""

    def default_driver(self) -> str:
        return self._settings(CacheSettings).default  # auto-loads + validates config("cache")

    def _build(self, url: str, **backend_options: Any) -> CacheRepository:
        from cashews import Cache

        client = Cache()
        client.setup(url, **backend_options)
        return CacheRepository(client)

    def create_array_driver(self) -> CacheRepository:
        return self._build("mem://")

    def create_redis_driver(self) -> CacheRepository:
        # cashews' Redis backend defaults suppress=True: a dead Redis silently no-ops — get
        # returns None, put is dropped, and a Cache.lock isn't a lock. Laravel raises on a dead
        # store; so must we, or cache-dependent correctness (locks, throttles) degrades silently.
        return self._build(self._settings(CacheSettings).url, suppress=False)


_CACHE_MISS: Any = object()


def cached(fn: Any = None, *, ttl: int | None = None, key: str | None = None) -> Any:
    """Memoize an **async** function's result in the default cache. Use bare (``@cached``) or with
    options (``@cached(ttl=300)``). The key defaults to the qualified name + the call's args; pass
    ``key=`` to fix it. A stored ``None`` is cached correctly (distinguished from a miss)."""
    if fn is None:

        def _decorate(f: Any) -> Any:
            return cached(f, ttl=ttl, key=key)

        return _decorate

    import functools

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        from arvel.support import cache

        cache_key = key or f"{fn.__module__}.{fn.__qualname__}:{args!r}:{sorted(kwargs.items())!r}"
        repo = cache()
        # Wrap in a 1-tuple so a cached None is never confused with a miss (the cache layer maps a
        # stored None to "absent"); the wrapper is always truthy/non-None.
        hit = await repo.get(cache_key, _CACHE_MISS)
        if hit is not _CACHE_MISS:
            return hit[0]
        result = await fn(*args, **kwargs)
        await repo.put(cache_key, (result,), ttl=ttl)
        return result

    return wrapper


__all__ = ["CacheManager", "CacheRepository", "CacheSettings", "cached"]
