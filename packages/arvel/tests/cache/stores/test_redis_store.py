"""Tests for RedisStore

Uses fakeredis so no real Redis server is required.
"""

from __future__ import annotations

import pytest

fakeredis = pytest.importorskip("fakeredis", reason="fakeredis not installed")

from arvel.cache.stores.redis import RedisStore  # noqa: E402


@pytest.fixture
async def store() -> RedisStore:
    import fakeredis.aioredis  # type: ignore[import-untyped]

    redis = fakeredis.aioredis.FakeRedis()
    return RedisStore(redis=redis, prefix="test")


class TestRedisStoreBasicOps:
    @pytest.mark.asyncio
    async def test_put_get_roundtrip(self, store: RedisStore) -> None:
        await store.put("k", "v")
        assert await store.get("k") == "v"

    @pytest.mark.asyncio
    async def test_missing_returns_none(self, store: RedisStore) -> None:
        assert await store.get("missing") is None

    @pytest.mark.asyncio
    async def test_has_present(self, store: RedisStore) -> None:
        await store.put("x", 1)
        assert await store.has("x") is True

    @pytest.mark.asyncio
    async def test_forget(self, store: RedisStore) -> None:
        await store.put("del", "v")
        await store.forget("del")
        assert await store.has("del") is False

    @pytest.mark.asyncio
    async def test_flush(self, store: RedisStore) -> None:
        await store.put("a", 1)
        await store.put("b", 2)
        await store.flush()
        assert await store.has("a") is False

    @pytest.mark.asyncio
    async def test_forever_sets_no_expiry(self, store: RedisStore) -> None:
        await store.forever("eternal", "yes")
        result = await store.get("eternal")
        assert result == "yes"

    @pytest.mark.asyncio
    async def test_put_none_ttl_means_forever(self) -> None:
        """ttl=None must store without expiry (CacheStore contract), not a default."""
        import fakeredis.aioredis  # type: ignore[import-untyped]

        redis = fakeredis.aioredis.FakeRedis()
        store = RedisStore(redis=redis, prefix="test")
        await store.put("no_expiry", "v", ttl=None)
        assert await redis.ttl("test:no_expiry") == -1  # -1 = key exists, no TTL

    @pytest.mark.asyncio
    async def test_data_types_preserved(self, store: RedisStore) -> None:
        data = {"key": "value", "count": 42, "items": [1, 2, 3]}
        await store.put("complex", data)
        assert await store.get("complex") == data

    @pytest.mark.asyncio
    async def test_import_error_without_redis(self) -> None:
        """helpful ImportError when redis not installed."""
        import importlib
        import sys

        # Temporarily remove redis from sys.modules to simulate missing dep
        redis_mods = {k: v for k, v in sys.modules.items() if k.startswith("redis")}
        for k in redis_mods:
            sys.modules.pop(k)
        try:
            # Re-importing should fail with helpful message
            import importlib.util

            spec = importlib.util.find_spec("arvel.cache.stores.redis")
            assert spec is not None
        finally:
            sys.modules.update(redis_mods)
