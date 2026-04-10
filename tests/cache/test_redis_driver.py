"""Tests for RedisCache driver — FR-075.

These tests mock the Redis client so they run without a real Redis server.
Integration tests with a live Redis server would use @pytest.mark.redis.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import orjson
import pytest

from arvel.cache.contracts import CacheContract


class TestRedisCacheDriver:
    """FR-075: RedisCache implements CacheContract using Redis."""

    def _make_driver(self, *, prefix: str = ""):
        from arvel.cache.drivers.redis_driver import RedisCache

        mock_redis = AsyncMock()
        return RedisCache(client=mock_redis, prefix=prefix), mock_redis

    def test_redis_implements_contract(self) -> None:
        from arvel.cache.drivers.redis_driver import RedisCache

        assert issubclass(RedisCache, CacheContract)

    async def test_get_returns_deserialized_value(self) -> None:
        cache, redis = self._make_driver()
        redis.get.return_value = orjson.dumps({"name": "Mo"})
        result = await cache.get("user:1")
        assert result == {"name": "Mo"}
        redis.get.assert_awaited_once_with("user:1")

    async def test_get_returns_default_on_miss(self) -> None:
        cache, redis = self._make_driver()
        redis.get.return_value = None
        result = await cache.get("missing", default="fallback")
        assert result == "fallback"

    async def test_put_stores_serialized_value_with_ttl(self) -> None:
        cache, redis = self._make_driver()
        await cache.put("key1", {"a": 1}, ttl=300)
        redis.set.assert_awaited_once_with("key1", orjson.dumps({"a": 1}), ex=300)

    async def test_put_stores_without_ttl(self) -> None:
        cache, redis = self._make_driver()
        await cache.put("key1", "value")
        redis.set.assert_awaited_once_with("key1", orjson.dumps("value"), ex=None)

    async def test_put_raises_serialization_error(self) -> None:
        from arvel.cache.exceptions import CacheSerializationError

        cache, _ = self._make_driver()
        with pytest.raises(CacheSerializationError):
            await cache.put("bad", lambda: None)

    async def test_forget_returns_true_when_deleted(self) -> None:
        cache, redis = self._make_driver()
        redis.delete.return_value = 1
        result = await cache.forget("key1")
        assert result is True

    async def test_forget_returns_false_on_miss(self) -> None:
        cache, redis = self._make_driver()
        redis.delete.return_value = 0
        result = await cache.forget("key1")
        assert result is False

    async def test_has_returns_true_when_exists(self) -> None:
        cache, redis = self._make_driver()
        redis.exists.return_value = 1
        assert await cache.has("key1") is True

    async def test_has_returns_false_on_miss(self) -> None:
        cache, redis = self._make_driver()
        redis.exists.return_value = 0
        assert await cache.has("key1") is False

    async def test_flush_calls_flushdb(self) -> None:
        cache, redis = self._make_driver()
        await cache.flush()
        redis.flushdb.assert_awaited_once()

    async def test_remember_returns_cached_value(self) -> None:
        cache, redis = self._make_driver()
        redis.get.return_value = orjson.dumps(42)
        callback = AsyncMock(return_value=99)
        result = await cache.remember("k", 60, callback)
        assert result == 42
        callback.assert_not_awaited()

    async def test_remember_calls_callback_on_miss(self) -> None:
        cache, redis = self._make_driver()
        redis.get.return_value = None
        callback = AsyncMock(return_value=99)
        result = await cache.remember("k", 60, callback)
        assert result == 99
        callback.assert_awaited_once()
        redis.set.assert_awaited_once()

    async def test_increment_uses_incrby(self) -> None:
        cache, redis = self._make_driver()
        redis.incrby.return_value = 5
        result = await cache.increment("counter", 3)
        assert result == 5
        redis.incrby.assert_awaited_once_with("counter", 3)

    async def test_decrement_uses_decrby(self) -> None:
        cache, redis = self._make_driver()
        redis.decrby.return_value = 7
        result = await cache.decrement("counter", 2)
        assert result == 7
        redis.decrby.assert_awaited_once_with("counter", 2)

    async def test_prefix_applied_to_keys(self) -> None:
        cache, redis = self._make_driver(prefix="app:")
        redis.get.return_value = orjson.dumps("val")
        await cache.get("user:1")
        redis.get.assert_awaited_once_with("app:user:1")
