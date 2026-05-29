"""Tests for Session Redis Store — FR-006-019."""

from __future__ import annotations

import pytest

fakeredis = pytest.importorskip("fakeredis", reason="fakeredis not installed")

from arvel.session.stores.redis import RedisSessionStore  # noqa: E402


@pytest.fixture
async def store() -> RedisSessionStore:
    import fakeredis.aioredis  # type: ignore[import-untyped]

    redis = fakeredis.aioredis.FakeRedis()
    return RedisSessionStore(redis=redis, prefix="arvel_session", lifetime=120)


class TestRedisSessionStore:
    @pytest.mark.asyncio
    async def test_read_write_roundtrip(self, store: RedisSessionStore) -> None:
        await store.write("sid1", {"user_id": 1}, lifetime=120)
        data = await store.read("sid1")
        assert data["user_id"] == 1

    @pytest.mark.asyncio
    async def test_missing_session_returns_empty(self, store: RedisSessionStore) -> None:
        data = await store.read("nonexistent")
        assert data == {}

    @pytest.mark.asyncio
    async def test_destroy_removes_session(self, store: RedisSessionStore) -> None:
        await store.write("sid2", {"k": "v"}, lifetime=120)
        await store.destroy("sid2")
        assert await store.read("sid2") == {}

    @pytest.mark.asyncio
    async def test_gc_is_noop_for_redis(self, store: RedisSessionStore) -> None:
        # Redis handles TTL natively; gc() should return 0 without error
        result = await store.gc(max_lifetime=120)
        assert result == 0
