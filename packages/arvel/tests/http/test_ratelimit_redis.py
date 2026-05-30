"""RedisStore — duck-typed against sync and async client doubles."""

from __future__ import annotations

import pytest
from arvel.http.ratelimit import RedisStore


class _SyncFakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key: str, seconds: int) -> None:
        self.expires[key] = seconds


class _AsyncFakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        self.expires[key] = seconds


@pytest.mark.asyncio
async def test_redis_store_sync_client() -> None:
    client = _SyncFakeRedis()
    store = RedisStore(client)

    a1 = await store.hit("ip:1.2.3.4", decay_seconds=60)
    a2 = await store.hit("ip:1.2.3.4", decay_seconds=60)

    assert a1.count == 1
    assert a2.count == 2
    # First hit sets expiry; second does not.
    assert len(client.expires) == 1


@pytest.mark.asyncio
async def test_redis_store_async_client() -> None:
    client = _AsyncFakeRedis()
    store = RedisStore(client)

    a1 = await store.hit("user:7", decay_seconds=30)
    a2 = await store.hit("user:7", decay_seconds=30)
    a3 = await store.hit("user:7", decay_seconds=30)

    assert (a1.count, a2.count, a3.count) == (1, 2, 3)
    assert client.expires == {"arvel:rl:" + RedisStore._hash_key("user:7"): 30}  # pyright: ignore[reportPrivateUsage]  # test asserts the private hash-key derivation matches at-rest format


@pytest.mark.asyncio
async def test_redis_store_rejects_client_without_incr_expire() -> None:
    class NotARedis:
        pass

    store = RedisStore(NotARedis())
    with pytest.raises(TypeError, match="incr/expire"):
        await store.hit("k", decay_seconds=1)


@pytest.mark.asyncio
async def test_redis_store_hashes_keys_to_avoid_pii_leakage() -> None:
    client = _SyncFakeRedis()
    store = RedisStore(client, key_prefix="rl:")

    await store.hit("user@example.com:login", decay_seconds=10)

    stored_keys = list(client.counts.keys())
    assert len(stored_keys) == 1
    assert "user@example.com" not in stored_keys[0]
    assert stored_keys[0].startswith("rl:")
