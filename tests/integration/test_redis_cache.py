"""Integration (doc 20/16) — the cache compiles + round-trips against a real Redis (cashews)."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.cache import CacheManager

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
