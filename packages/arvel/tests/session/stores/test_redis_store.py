"""Tests for Session Redis Store."""

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

    @pytest.mark.asyncio
    async def test_encrypted_roundtrip_handles_bytes_payload(self) -> None:
        # redis-py returns bytes by default; the encrypted read path must decode
        # before handing the token to the cipher (regression: AttributeError on
        # bytes.encode()).
        import fakeredis.aioredis
        from arvel.session.cipher import SessionCipher

        cipher = SessionCipher.from_app_key(b"0" * 32)
        redis = fakeredis.aioredis.FakeRedis()
        store = RedisSessionStore(redis=redis, prefix="enc:", lifetime=120, cipher=cipher)

        await store.write("sid", {"user_id": 7}, lifetime=120)
        raw = await redis.get("enc:sid")
        assert isinstance(raw, bytes) and b"user_id" not in raw  # actually encrypted
        assert (await store.read("sid"))["user_id"] == 7
