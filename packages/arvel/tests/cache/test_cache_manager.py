"""Tests for CacheManager — FR-006-001..007, FR-006-013..015."""

from __future__ import annotations

import pytest
from arvel.cache import CacheManager
from arvel.cache.stores.array import ArrayStore
from arvel.config.cache_config import CacheConfig, CacheDriver
from arvel.facades import Cache
from pydantic import ValidationError


class TestCacheManagerDriverSelection:
    """FR-006-001: CacheManager returns the configured store."""

    def test_default_store_is_array(self) -> None:
        manager = CacheManager(CacheConfig(connection=CacheDriver.ARRAY))
        store = manager.store()
        assert isinstance(store, ArrayStore)

    def test_named_store_selection(self) -> None:
        manager = CacheManager(CacheConfig(connection=CacheDriver.NULL))
        from arvel.cache.stores.null import NullStore

        store = manager.store()
        assert isinstance(store, NullStore)

    def test_unknown_store_raises(self) -> None:
        with pytest.raises(ValidationError):
            CacheConfig.model_validate({"connection": "nonexistent"})


class TestCacheManagerDelegation:
    """FR-006-001..007: CacheManager delegates to active store correctly."""

    @pytest.mark.asyncio
    async def test_put_and_get(self, cache_manager: CacheManager) -> None:
        await cache_manager.put("key", "value", ttl=60)
        assert await cache_manager.get("key") == "value"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, cache_manager: CacheManager) -> None:
        assert await cache_manager.get("missing") is None

    @pytest.mark.asyncio
    async def test_get_with_default(self, cache_manager: CacheManager) -> None:
        result = await cache_manager.get("missing", default="fallback")
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_has_true_when_present(self, cache_manager: CacheManager) -> None:
        await cache_manager.put("present", 1)
        assert await cache_manager.has("present") is True

    @pytest.mark.asyncio
    async def test_has_false_when_absent(self, cache_manager: CacheManager) -> None:
        assert await cache_manager.has("absent") is False

    @pytest.mark.asyncio
    async def test_forget_removes_key(self, cache_manager: CacheManager) -> None:
        await cache_manager.put("del", "v")
        assert await cache_manager.forget("del") is True
        assert await cache_manager.has("del") is False

    @pytest.mark.asyncio
    async def test_flush_empties_store(self, cache_manager: CacheManager) -> None:
        await cache_manager.put("a", 1)
        await cache_manager.put("b", 2)
        await cache_manager.flush()
        assert await cache_manager.has("a") is False

    @pytest.mark.asyncio
    async def test_forever_never_expires(self, cache_manager: CacheManager) -> None:
        await cache_manager.forever("eternal", "yes")
        assert await cache_manager.get("eternal") == "yes"


class TestCacheManagerRemember:
    """FR-006-007: remember[T] lazy population."""

    @pytest.mark.asyncio
    async def test_remember_calls_callback_on_miss(self, cache_manager: CacheManager) -> None:
        calls = 0

        async def compute() -> str:
            nonlocal calls
            calls += 1
            return "computed"

        result = await cache_manager.remember("k", ttl=60, callback=compute)
        assert result == "computed"
        assert calls == 1

    @pytest.mark.asyncio
    async def test_remember_returns_cached_on_hit(self, cache_manager: CacheManager) -> None:
        calls = 0

        async def compute() -> str:
            nonlocal calls
            calls += 1
            return "computed"

        await cache_manager.remember("k", ttl=60, callback=compute)
        result2 = await cache_manager.remember("k", ttl=60, callback=compute)
        assert result2 == "computed"
        assert calls == 1  # callback not called again

    @pytest.mark.asyncio
    async def test_remember_does_not_cache_on_exception(self, cache_manager: CacheManager) -> None:
        async def failing() -> str:
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            await cache_manager.remember("k", ttl=60, callback=failing)

        assert await cache_manager.has("k") is False


class TestCacheFacade:
    """FR-006-015: Cache facade classmethod API."""

    def test_facade_not_bound_raises(self) -> None:
        from arvel.cache.exceptions import FacadeNotBoundError

        Cache.manager = None
        with pytest.raises(FacadeNotBoundError):
            Cache.mgr()

    def test_facade_bind_connects_manager(self) -> None:
        from arvel.cache import CacheManager
        from arvel.config.cache_config import CacheConfig
        from arvel.container import Container

        container = Container()
        manager = CacheManager(CacheConfig(connection=CacheDriver.NULL))
        container.instance(CacheManager, manager)
        Cache.bind(container)
        assert Cache.manager is manager

    @pytest.mark.asyncio
    async def test_facade_delegates_store_operations(self) -> None:
        async def compute() -> str:
            return "computed"

        with Cache.fake():
            await Cache.put("forgotten", "value")
            assert await Cache.has("forgotten") is True
            assert await Cache.forget("forgotten") is True
            assert await Cache.has("forgotten") is False

            await Cache.forever("forever", "value")
            assert await Cache.get("forever") == "value"
            assert await Cache.remember("remembered", 60, compute) == "computed"

            assert Cache.tags(["users"]) is not None
            assert Cache.lock("cache-facade-lock", ttl=10) is not None
            assert Cache.rate_limiter() is not None

            await Cache.flush()
            assert await Cache.has("forever") is False
