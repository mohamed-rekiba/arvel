"""Cache subsystem — manager, protocol, and public re-exports."""

from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from arvel.cache.exceptions import CacheException, FacadeNotBoundError, TagsNotSupported
from arvel.cache.locks import AtomicLockStore, CacheLock
from arvel.cache.rate_limiter import RateLimiter
from arvel.cache.store import CacheStore
from arvel.cache.tags import TaggedCache
from arvel.cache.versioner import CacheVersioner
from arvel.config.cache_config import CacheDriver

T = TypeVar("T")


class CacheManager:
    """Driver factory for the cache subsystem.

    Holds a dict of resolved stores keyed by driver name. The default store is
    resolved once lazily on first access.
    """

    def __init__(self, config: Any) -> None:
        self._config = config
        self._stores: dict[CacheDriver, CacheStore] = {}

    @property
    def config(self) -> Any:
        return self._config

    def store(self, name: CacheDriver | str | None = None) -> CacheStore:
        """Return the named (or default) cache store."""
        driver = self._config.driver if name is None else CacheDriver(name)
        if driver not in self._stores:
            self._stores[driver] = self._make_store(driver)
        return self._stores[driver]

    def _make_store(self, driver: CacheDriver) -> CacheStore:
        if driver == CacheDriver.ARRAY:
            from arvel.cache.stores.array import ArrayStore

            return ArrayStore(prefix=self._config.prefix)
        if driver == CacheDriver.FILE:
            from arvel.cache.stores.file import FileStore

            return FileStore(path=Path(self._config.file_path), prefix=self._config.prefix)
        if driver == CacheDriver.NULL:
            from arvel.cache.stores.null import NullStore

            return NullStore()
        if driver == CacheDriver.REDIS:
            from typing import cast

            from arvel.cache.stores.redis import RedisConn, RedisStore

            try:
                _aioredis = importlib.import_module("redis.asyncio")
            except ImportError as exc:
                raise ImportError(
                    "CacheManager redis driver requires arvel[redis]. "
                    "Install with: pip install 'arvel[redis]'"
                ) from exc

            url: str | None = getattr(self._config, "url", None)
            if url:
                client: RedisConn = cast(
                    "RedisConn", _aioredis.from_url(url, decode_responses=False)
                )
            else:
                client = cast(
                    "RedisConn",
                    _aioredis.Redis(
                        host=getattr(self._config, "host", "localhost"),
                        port=getattr(self._config, "port", 6379),
                        db=getattr(self._config, "database", 0),
                        password=getattr(self._config, "password", None) or None,
                    ),
                )
            return RedisStore(redis=client, prefix=self._config.prefix)
        if driver == CacheDriver.DATABASE:
            from arvel.cache.stores.database import DatabaseStore
            from arvel.database.db import DB

            # Share the app's default DB connection. A throwaway in-memory engine
            # would make the cache per-process and ephemeral — useless for a
            # database cache. Run the published cache migration to create the table.
            maker = DB.session_maker_for()
            return DatabaseStore(session_maker=maker, prefix=self._config.prefix)
        raise ValueError(f"Unknown cache driver: {driver!r}")

    def tags(self, tags: list[str]) -> TaggedCache:
        """Return a TaggedCache scoped to the given tags."""
        return TaggedCache(store=self.store(), tags=tags)

    def lock(self, name: str, ttl: int = 0) -> CacheLock:
        """Return a CacheLock for the given name."""
        store = self.store()
        if not isinstance(store, AtomicLockStore):
            import warnings

            warnings.warn(
                f"{type(store).__name__} provides process-local locks only; "
                "distributed-lock semantics require the Redis store.",
                RuntimeWarning,
                stacklevel=2,
            )
        return CacheLock(store=store, name=name, ttl=ttl)

    def rate_limiter(self) -> RateLimiter:
        """Return a RateLimiter backed by the default store."""
        return RateLimiter(store=self.store())

    async def put(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self.store().put(key, value, ttl=ttl)

    async def get(self, key: str, default: Any = None) -> Any | None:
        return await self.store().get(key, default)

    async def forget(self, key: str) -> bool:
        return await self.store().forget(key)

    async def has(self, key: str) -> bool:
        return await self.store().has(key)

    async def flush(self) -> None:
        await self.store().flush()

    async def forever(self, key: str, value: Any) -> None:
        await self.store().forever(key, value)

    async def remember(self, key: str, ttl: int, callback: Callable[[], Awaitable[T]]) -> T:
        """Return cached value or call ``callback``, cache the result, and return it."""
        cached = await self.get(key)
        if cached is not None or await self.has(key):
            return cached  # type: ignore[return-value]
        value = await callback()
        await self.put(key, value, ttl=ttl)
        return value


__all__ = [
    "CacheException",
    "CacheLock",
    "CacheManager",
    "CacheStore",
    "CacheVersioner",
    "FacadeNotBoundError",
    "RateLimiter",
    "TaggedCache",
    "TagsNotSupported",
]
