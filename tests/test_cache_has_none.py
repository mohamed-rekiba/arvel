"""has() reports presence, not truthiness — a stored None is still present (round H10)."""

from __future__ import annotations

import pytest

from arvel.cache import CacheRepository


@pytest.fixture
def cache() -> CacheRepository:
    import cashews

    client = cashews.Cache()
    client.setup("mem://")
    return CacheRepository(client)


@pytest.mark.asyncio
async def test_has_true_for_stored_none(cache: CacheRepository) -> None:
    await cache.put("k", None)
    assert await cache.has("k") is True
    # has() is the disambiguator; get() keeps standard cache semantics (a default fills a None value)
    assert await cache.get("k") is None
    assert await cache.get("k", "sentinel") == "sentinel"


@pytest.mark.asyncio
async def test_has_false_after_forget(cache: CacheRepository) -> None:
    await cache.put("k", None)
    await cache.forget("k")
    assert await cache.has("k") is False


@pytest.mark.asyncio
async def test_has_false_for_absent(cache: CacheRepository) -> None:
    assert await cache.has("never-set") is False
