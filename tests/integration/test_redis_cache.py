"""Integration (doc 20/16, spec 06-cache-parity) — the cache compiles + round-trips against a
real Redis (cashews), including the Laravel-parity verbs, atomic locks, tags, and the direct
Redis facade (command/pipeline/pub-sub)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from arvel.cache import CacheManager
from arvel.cache.redis import RedisManager

pytestmark = pytest.mark.integration


async def test_cache_roundtrip_on_redis(redis_url: str, configure_app: Any) -> None:
    app = configure_app(cache={"default": "redis", "url": redis_url})
    cache = CacheManager(app).driver("redis")

    await cache.put("user:1", {"name": "Ada"}, ttl=60)
    assert await cache.get("user:1") == {"name": "Ada"}
    assert await cache.has("user:1") is True

    calls: list[int] = []

    async def compute() -> int:
        calls.append(1)
        return 42

    assert await cache.remember("answer", 60, compute) == 42
    assert await cache.remember("answer", 60, compute) == 42  # served from Redis, not recomputed
    assert len(calls) == 1

    await cache.forget("user:1")
    assert await cache.get("user:1") is None


async def test_concurrent_increments_are_atomic_on_redis(
    redis_url: str, configure_app: Any
) -> None:
    app = configure_app(cache={"default": "redis", "url": redis_url})
    cache = CacheManager(app).driver("redis")

    await asyncio.gather(*(cache.increment("counter", 10) for _ in range(20)))
    assert await cache.get("counter") == 200


async def test_add_race_exactly_one_winner_on_redis(redis_url: str, configure_app: Any) -> None:
    app = configure_app(cache={"default": "redis", "url": redis_url})
    cache = CacheManager(app).driver("redis")

    results = await asyncio.gather(*(cache.add("nx-race", i) for i in range(10)))
    assert results.count(True) == 1
    assert results.count(False) == 9


async def test_lock_contention_across_connections_with_lua_owner_release(
    redis_url: str, configure_app: Any
) -> None:
    """Two *separate* cashews connections (≈ two worker processes) contend for one redis lock;
    only the true owner's release (the Lua compare-and-delete) actually frees it."""
    app = configure_app(cache={"default": "redis", "url": redis_url})
    cache_a = CacheManager(app).driver("redis")  # its own cashews Cache + connection pool
    cache_b = CacheManager(app).driver("redis")  # a second, independent connection

    lock_a = cache_a.lock("report:daily", seconds=30)
    lock_b = cache_b.lock("report:daily", seconds=30)

    assert await lock_a.acquire() is True
    assert await lock_b.acquire() is False  # held cross-connection

    assert await lock_b.release() is False  # non-owner: Lua script refuses
    assert await lock_a.release() is True  # true owner: Lua compare-and-delete succeeds

    assert await lock_b.acquire() is True  # free again
    assert await lock_b.release() is True


async def test_tags_flush_isolated_on_redis(redis_url: str, configure_app: Any) -> None:
    app = configure_app(cache={"default": "redis", "url": redis_url})
    cache = CacheManager(app).driver("redis")

    await cache.tags("people").put("k1", "v1")
    await cache.tags("artists").put("k2", "v2")
    await cache.put("k3", "v3")  # untagged

    assert await cache.tags("people").flush() is True

    assert await cache.tags("people").get("k1") is None
    assert await cache.tags("artists").get("k2") == "v2"
    assert await cache.get("k3") == "v3"


async def test_flexible_swr_observed_against_redis(redis_url: str, configure_app: Any) -> None:
    app = configure_app(cache={"default": "redis", "url": redis_url})
    cache = CacheManager(app).driver("redis")
    calls = {"n": 0}

    async def compute() -> int:
        calls["n"] += 1
        return calls["n"]

    assert await cache.flexible("swr", (1, 5), compute) == 1
    await asyncio.sleep(1.2)  # past fresh (1s), within stale (5s)
    assert await cache.flexible("swr", (1, 5), compute) == 1  # stale value, background refresh
    await cache.wait_for_pending_revalidations()
    assert calls["n"] == 2

    assert await cache.flexible("swr", (1, 5), compute) == 2  # fresh again after revalidation


async def test_redis_facade_command_round_trip(redis_url: str, configure_app: Any) -> None:
    app = configure_app(redis={"url": redis_url})
    manager = RedisManager(app)
    try:
        conn = manager.connection()
        assert await conn.command("SET", "greeting", "hi") is True
        assert await conn.command("GET", "greeting") == b"hi"
    finally:
        await manager.close_all()


async def test_redis_facade_pipeline_batches_n_ops_in_one_round_trip(
    redis_url: str, configure_app: Any
) -> None:
    app = configure_app(redis={"url": redis_url})
    manager = RedisManager(app)
    try:
        conn = manager.connection()
        async with conn.pipeline() as pipe:
            for i in range(5):
                pipe.command("SET", f"pk:{i}", str(i))
            results = await pipe.execute()
        assert len(results) == 5
        assert all(results)
        for i in range(5):
            assert await conn.command("GET", f"pk:{i}") == str(i).encode()
    finally:
        await manager.close_all()


async def test_redis_facade_publish_subscribe_round_trip(
    redis_url: str, configure_app: Any
) -> None:
    app = configure_app(redis={"url": redis_url})
    manager = RedisManager(app)
    try:
        conn = manager.connection()
        received: list[str] = []

        async def consume() -> None:
            async for message in conn.subscribe("channel:test"):
                received.append(message)
                break

        consumer = asyncio.create_task(consume())
        await asyncio.sleep(0.2)  # let the subscriber attach before publishing
        await conn.publish("channel:test", "hello")
        await asyncio.wait_for(consumer, timeout=5)

        assert received == ["hello"]
    finally:
        await manager.close_all()


async def test_redis_facade_eval(redis_url: str, configure_app: Any) -> None:
    app = configure_app(redis={"url": redis_url})
    manager = RedisManager(app)
    try:
        conn = manager.connection()
        result = await conn.eval("return ARGV[1]", args=["42"])
        assert result == b"42"
    finally:
        await manager.close_all()
