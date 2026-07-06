"""Cache (doc 16, spec 06-cache-parity §1) — parity verbs on the array driver:
add/pull/forever/touch/decrement."""

from __future__ import annotations

from typing import Any

from arvel.cache import CacheManager


def _cache() -> Any:
    return CacheManager().driver()


async def test_add_stores_only_when_absent() -> None:
    cache = _cache()
    assert await cache.add("k", "first") is True
    assert await cache.get("k") == "first"
    assert await cache.add("k", "second") is False  # already present → no overwrite
    assert await cache.get("k") == "first"


async def test_pull_returns_then_deletes() -> None:
    cache = _cache()
    await cache.put("k", "v")
    assert await cache.pull("k") == "v"
    assert await cache.get("k") is None  # gone after pull
    assert await cache.pull("missing", "default") == "default"


async def test_forever_persists_without_ttl() -> None:
    cache = _cache()
    assert await cache.forever("k", "v") is True
    assert await cache.get("k") == "v"


async def test_touch_is_expire_alias() -> None:
    cache = _cache()
    await cache.put("k", "v", ttl=None)
    assert await cache.touch("k", 60) is True
    assert await cache.get("k") == "v"  # still present, TTL refreshed


async def test_decrement_mirrors_increment() -> None:
    cache = _cache()
    assert await cache.increment("counter", 10) == 10
    assert await cache.decrement("counter", 3) == 7
    assert await cache.decrement("counter") == 6


async def test_add_race_only_one_winner() -> None:
    """Concurrent `add()` calls on the same key: exactly one stores (NX semantics)."""
    import asyncio

    cache = _cache()
    results = await asyncio.gather(*(cache.add("race", i) for i in range(20)))
    assert results.count(True) == 1
    assert results.count(False) == 19


async def test_put_with_non_positive_ttl_stores_nothing() -> None:
    cache = _cache()
    assert await cache.put("k", "v", ttl=0) is False
    assert await cache.has("k") is False
    assert await cache.put("k2", "v", ttl=-5) is False
    assert await cache.has("k2") is False


async def test_put_non_positive_ttl_evicts_an_existing_value() -> None:
    cache = _cache()
    await cache.put("k", "v")
    assert await cache.put("k", "v2", ttl=0) is False
    assert await cache.has("k") is False


async def test_add_with_non_positive_ttl_stores_nothing() -> None:
    cache = _cache()
    assert await cache.add("k", "v", ttl=0) is False
    assert await cache.has("k") is False
