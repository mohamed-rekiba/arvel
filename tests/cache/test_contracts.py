"""Tests for CacheContract and drivers — Story 1.

FR-067: CacheContract ABC with get, put, forget, has, flush, remember, increment, decrement.
FR-068: put(key, value, ttl) stores JSON-serialized value with TTL.
FR-069: get(key, default) returns deserialized value or default.
FR-070: remember(key, ttl, callback) returns cached or computes.
FR-071: forget(key) removes key and returns bool.
FR-072: flush() removes all keys.
FR-073: has(key) checks existence and expiry.
FR-074: increment/decrement atomically adjust integer value.
FR-076: MemoryCache implements CacheContract.
FR-077: NullCache implements CacheContract.
NFR-030: MemoryCache get/put < 1ms.
"""

from __future__ import annotations

import pytest

from arvel.cache.contracts import CacheContract


class TestCacheContractInterface:
    """FR-067: CacheContract ABC defines required methods."""

    def test_cache_contract_is_abstract(self) -> None:
        abstract_cls: type = CacheContract
        with pytest.raises(TypeError):
            abstract_cls()

    @pytest.mark.parametrize(
        "method",
        [
            "get",
            "put",
            "forget",
            "has",
            "flush",
            "remember",
            "increment",
            "decrement",
        ],
    )
    def test_contract_has_method(self, method: str) -> None:
        assert hasattr(CacheContract, method)


class TestMemoryCacheDriver:
    """FR-076: MemoryCache — in-process dict with TTL expiry."""

    async def test_memory_implements_contract(self) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        assert isinstance(cache, CacheContract)

    async def test_put_and_get(self) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        await cache.put("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    async def test_get_returns_default_on_miss(self) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        result = await cache.get("missing", default="fallback")
        assert result == "fallback"

    async def test_get_returns_none_on_miss_no_default(self) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        result = await cache.get("missing")
        assert result is None

    async def test_put_with_ttl_expires(self) -> None:
        """FR-068: TTL expiry — value disappears after TTL."""
        from unittest.mock import patch

        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        await cache.put("temp", "data", ttl=1)

        assert await cache.has("temp") is True

        with patch("time.monotonic", return_value=9999999999.0):
            result = await cache.get("temp")
            assert result is None

    async def test_forget_existing_key(self) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        await cache.put("key", "val")
        removed = await cache.forget("key")
        assert removed is True
        assert await cache.has("key") is False

    async def test_forget_missing_key(self) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        removed = await cache.forget("nope")
        assert removed is False

    async def test_has_existing_key(self) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        await cache.put("exists", 42)
        assert await cache.has("exists") is True

    async def test_has_missing_key(self) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        assert await cache.has("nope") is False

    async def test_flush_removes_all(self) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        await cache.put("a", 1)
        await cache.put("b", 2)
        await cache.flush()
        assert await cache.has("a") is False
        assert await cache.has("b") is False

    async def test_remember_cache_miss(self) -> None:
        """FR-070: On miss, await callback, cache result, return it."""
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        call_count = 0

        async def expensive():
            nonlocal call_count
            call_count += 1
            return {"user": "Mo"}

        result = await cache.remember("profile", 60, expensive)
        assert result == {"user": "Mo"}
        assert call_count == 1

        result2 = await cache.remember("profile", 60, expensive)
        assert result2 == {"user": "Mo"}
        assert call_count == 1  # callback NOT called again

    async def test_remember_callback_error_propagates(self) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()

        async def failing():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await cache.remember("fail", 60, failing)

        assert await cache.has("fail") is False

    async def test_increment(self) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        await cache.put("counter", 10)
        result = await cache.increment("counter", 5)
        assert result == 15

    async def test_decrement(self) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        await cache.put("counter", 10)
        result = await cache.decrement("counter", 3)
        assert result == 7

    async def test_increment_nonexistent_key(self) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        result = await cache.increment("new_counter")
        assert result == 1

    async def test_put_complex_types(self) -> None:
        """FR-068: JSON serialization via orjson for complex types."""
        from arvel.cache.drivers.memory_driver import MemoryCache

        cache = MemoryCache()
        await cache.put("data", {"users": [1, 2, 3], "active": True})
        result = await cache.get("data")
        assert result == {"users": [1, 2, 3], "active": True}


class TestNullCacheDriver:
    """FR-077: NullCache — writes discard, reads return default."""

    async def test_null_implements_contract(self) -> None:
        from arvel.cache.drivers.null_driver import NullCache

        cache = NullCache()
        assert isinstance(cache, CacheContract)

    async def test_null_put_discards(self) -> None:
        from arvel.cache.drivers.null_driver import NullCache

        cache = NullCache()
        await cache.put("key", "value")
        assert await cache.get("key") is None

    async def test_null_has_always_false(self) -> None:
        from arvel.cache.drivers.null_driver import NullCache

        cache = NullCache()
        assert await cache.has("anything") is False

    async def test_null_forget_returns_false(self) -> None:
        from arvel.cache.drivers.null_driver import NullCache

        cache = NullCache()
        assert await cache.forget("key") is False

    async def test_null_remember_always_calls_callback(self) -> None:
        from arvel.cache.drivers.null_driver import NullCache

        cache = NullCache()
        count = 0

        async def cb():
            nonlocal count
            count += 1
            return "fresh"

        result = await cache.remember("key", 60, cb)
        assert result == "fresh"
        assert count == 1

        result2 = await cache.remember("key", 60, cb)
        assert result2 == "fresh"
        assert count == 2  # always calls — never caches


class TestCacheSerializationError:
    """FR-079: Non-serializable values raise CacheSerializationError."""

    async def test_non_serializable_raises_error(self) -> None:
        from arvel.cache.drivers.memory_driver import MemoryCache
        from arvel.cache.exceptions import CacheSerializationError

        cache = MemoryCache()

        with pytest.raises(CacheSerializationError) as exc_info:
            await cache.put("bad", lambda x: x)

        assert "bad" in str(exc_info.value)

    def test_error_includes_key_and_type(self) -> None:
        from arvel.cache.exceptions import CacheSerializationError

        err = CacheSerializationError("my_key", "set")
        assert err.key == "my_key"
        assert err.value_type == "set"
        assert "my_key" in str(err)
        assert "set" in str(err)
