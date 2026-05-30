"""Tests for CacheVersioner — FR-032-07 / AC-17..18.

Tests are written RED — arvel.cache.CacheVersioner does not exist yet.
"""

from __future__ import annotations

import pytest
from arvel.cache.stores.array import ArrayStore


@pytest.fixture
def array_store() -> ArrayStore:
    return ArrayStore(prefix="test")


# ─── AC-17: invalidate() changes versioned keys ──────────────────────────────


@pytest.mark.asyncio
async def test_invalidate_changes_versioned_keys(array_store: ArrayStore) -> None:
    from arvel.cache import CacheVersioner

    v = CacheVersioner("items:list", store=array_store)
    key_before = await v.versioned_key("user:1", "page:1")
    await v.invalidate()
    key_after = await v.versioned_key("user:1", "page:1")
    assert key_before != key_after


@pytest.mark.asyncio
async def test_versioned_key_stable_until_invalidation(array_store: ArrayStore) -> None:
    from arvel.cache import CacheVersioner

    v = CacheVersioner("items:list", store=array_store)
    key1 = await v.versioned_key("user:42")
    key2 = await v.versioned_key("user:42")
    assert key1 == key2, "Key must be stable before invalidation"


@pytest.mark.asyncio
async def test_invalidate_multiple_times(array_store: ArrayStore) -> None:
    from arvel.cache import CacheVersioner

    v = CacheVersioner("items:list", store=array_store)
    keys: set[str] = set()
    for _ in range(3):
        keys.add(await v.versioned_key("user:1"))
        await v.invalidate()
    assert len(keys) == 3, "Each invalidation must produce a different key"


# ─── AC-18: No key collision between versioners ───────────────────────────────


@pytest.mark.asyncio
async def test_no_collision_between_different_prefixes(array_store: ArrayStore) -> None:
    from arvel.cache import CacheVersioner

    v1 = CacheVersioner("items:list", store=array_store)
    v2 = CacheVersioner("users:list", store=array_store)

    key_v2_before = await v2.versioned_key("page:1")
    await v1.invalidate()
    key_v2_after = await v2.versioned_key("page:1")
    assert key_v2_before == key_v2_after


# ─── importable from arvel.cache ──────────────────────────────────────────────


def test_importable_from_arvel_cache() -> None:
    from arvel.cache import CacheVersioner

    assert callable(CacheVersioner)


def test_importable_from_arvel_cache_versioner() -> None:
    from arvel.cache.versioner import CacheVersioner

    assert callable(CacheVersioner)
