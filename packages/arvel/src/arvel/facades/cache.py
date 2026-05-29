"""Cache facade — @classmethod API proxying to the bound CacheManager."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from arvel.cache.exceptions import FacadeNotBoundError

if TYPE_CHECKING:
    from arvel.cache import CacheLock, CacheManager, CacheStore, RateLimiter, TaggedCache
    from arvel.container import Container
    from arvel.testing.fakes.cache import CacheFakeContext

T = TypeVar("T")


class Cache:
    """Facade providing a classmethod API for the cache subsystem.

    Bound by ``CacheServiceProvider.register()``.
    """

    manager: ClassVar[CacheManager | None] = None

    @classmethod
    def bind(cls, container: Container) -> None:
        from arvel.cache import CacheManager

        cls.manager = container.make(CacheManager)

    @classmethod
    def mgr(cls) -> CacheManager:
        if cls.manager is None:
            raise FacadeNotBoundError("Cache")
        return cls.manager

    @classmethod
    def store(cls, name: str | None = None) -> CacheStore:
        return cls.mgr().store(name)

    @classmethod
    async def put(cls, key: str, value: Any, ttl: int | None = None) -> None:
        await cls.mgr().put(key, value, ttl=ttl)

    @classmethod
    async def get(cls, key: str, default: Any = None) -> Any | None:
        return await cls.mgr().get(key, default)

    @classmethod
    async def forget(cls, key: str) -> bool:
        return await cls.mgr().forget(key)

    @classmethod
    async def has(cls, key: str) -> bool:
        return await cls.mgr().has(key)

    @classmethod
    async def flush(cls) -> None:
        await cls.mgr().flush()

    @classmethod
    def fake(cls) -> CacheFakeContext:
        """Swap in an ARRAY-backed CacheManager for tests.

        Usage::

            with Cache.fake():
                await Cache.put("k", "v", ttl=60)
                Cache.assert_stored("k")
        """
        from arvel.testing.fakes.cache import CacheFakeContext

        return CacheFakeContext()

    @classmethod
    def assert_stored(cls, key: str) -> None:
        """Assert that ``key`` has a value in the (array-backed) test cache.

        Requires the cache to be in fake mode (``Cache.fake()`` returned an
        ArrayStore-backed manager). Pokes the in-memory dict directly so the
        call is sync-safe inside async tests.
        """
        store = cls.mgr().store()
        entries = getattr(store, "entries", None)
        if entries is None:
            raise AssertionError("Cache.assert_stored requires Cache.fake() context")
        prefix = getattr(cls.mgr(), "prefix", "")
        full_key = f"{prefix}{key}"
        # Walk both prefixed and unprefixed forms — manager wrapping varies.
        if not any(k.endswith(f":{key}") or k in (key, full_key) for k in entries):
            raise AssertionError(f"Cache key {key!r} is missing")

    @classmethod
    def assert_missing(cls, key: str) -> None:
        """Assert that ``key`` is NOT in the (array-backed) test cache."""
        store = cls.mgr().store()
        entries = getattr(store, "entries", None)
        if entries is None:
            raise AssertionError("Cache.assert_missing requires Cache.fake() context")
        if any(k.endswith(f":{key}") or k == key for k in entries):
            raise AssertionError(f"Cache key {key!r} is present but should be missing")

    @classmethod
    async def forever(cls, key: str, value: Any) -> None:
        await cls.mgr().forever(key, value)

    @classmethod
    async def remember(cls, key: str, ttl: int, callback: Callable[[], Awaitable[T]]) -> T:
        return await cls.mgr().remember(key, ttl, callback)

    @classmethod
    def tags(cls, tags: list[str]) -> TaggedCache:
        return cls.mgr().tags(tags)

    @classmethod
    def lock(cls, name: str, ttl: int = 0) -> CacheLock:
        return cls.mgr().lock(name, ttl=ttl)

    @classmethod
    def rate_limiter(cls) -> RateLimiter:
        return cls.mgr().rate_limiter()


__all__ = ["Cache"]
