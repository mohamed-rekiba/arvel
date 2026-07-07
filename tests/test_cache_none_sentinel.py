"""Cache (backlog 6.1) — a stored None is a hit, not a miss, across get/pull/remember.

The repository wraps stored values in its own envelope (`arvel.cache._wrap`/`_unwrap`) so a
cached None is never confused with "nothing stored". Written test-first.
"""

from __future__ import annotations

import pytest

from arvel.cache import CacheManager, CacheRepository


@pytest.fixture
def cache() -> CacheRepository:
    return CacheManager().driver()


async def test_get_returns_stored_none_not_default(cache: CacheRepository) -> None:
    await cache.put("k", None)
    assert await cache.get("k", "default") is None


async def test_get_default_still_applies_on_a_real_miss(cache: CacheRepository) -> None:
    assert await cache.get("never-set", "default") == "default"


async def test_pull_returns_stored_none_and_deletes_it(cache: CacheRepository) -> None:
    await cache.put("k", None)
    assert await cache.pull("k", "default") is None
    assert await cache.has("k") is False


async def test_remember_does_not_recompute_a_cached_none(cache: CacheRepository) -> None:
    calls = {"n": 0}

    async def compute() -> None:
        calls["n"] += 1
        return None

    assert await cache.remember("k", 60, compute) is None
    assert await cache.remember("k", 60, compute) is None  # served from cache, not recomputed
    assert calls["n"] == 1


async def test_round_trip_survives_non_none_values_too(cache: CacheRepository) -> None:
    """The envelope is symmetric — ordinary values keep working exactly as before."""
    await cache.put("k", "v")
    assert await cache.get("k") == "v"
    assert await cache.pull("k") == "v"


async def test_foreign_raw_value_read_best_effort(cache: CacheRepository) -> None:
    """A value written directly through the underlying client (not via arvel's put/add) has no
    envelope — get() passes it through unchanged rather than crashing on the unfamiliar shape."""
    await cache.client.set("k", "raw-value")
    assert await cache.get("k") == "raw-value"
