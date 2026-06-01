"""Tests for ArrayStore."""

from __future__ import annotations

import time
from typing import Any

import pytest
from arvel.cache.stores.array import ArrayStore


@pytest.fixture
def store() -> ArrayStore:
    return ArrayStore(prefix="test")


class TestArrayStoreBasicOps:
    @pytest.mark.asyncio
    async def test_put_get_roundtrip(self, store: ArrayStore) -> None:
        await store.put("k", "v", ttl=60)
        assert await store.get("k") == "v"

    @pytest.mark.asyncio
    async def test_missing_returns_none(self, store: ArrayStore) -> None:
        assert await store.get("missing") is None

    @pytest.mark.asyncio
    async def test_has_present(self, store: ArrayStore) -> None:
        await store.put("x", 1)
        assert await store.has("x") is True

    @pytest.mark.asyncio
    async def test_has_absent(self, store: ArrayStore) -> None:
        assert await store.has("absent") is False

    @pytest.mark.asyncio
    async def test_forget_existing_key(self, store: ArrayStore) -> None:
        await store.put("del", "v")
        result = await store.forget("del")
        assert result is True
        assert await store.has("del") is False

    @pytest.mark.asyncio
    async def test_forget_missing_key(self, store: ArrayStore) -> None:
        result = await store.forget("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_flush_empties_store(self, store: ArrayStore) -> None:
        await store.put("a", 1)
        await store.put("b", 2)
        await store.flush()
        assert await store.has("a") is False
        assert await store.has("b") is False

    @pytest.mark.asyncio
    async def test_forever_no_expiry(self, store: ArrayStore) -> None:
        await store.forever("eternal", "yes")
        assert await store.get("eternal") == "yes"


class TestArrayStoreTTL:
    @pytest.mark.asyncio
    async def test_expired_key_returns_none(self, store: ArrayStore) -> None:
        await store.put("soon", "v", ttl=1)
        # Manually advance the stored expiry to the past
        store.entries["test:soon"] = store.entries["test:soon"]._replace(
            expires_at=time.monotonic() - 1
        )
        assert await store.get("soon") is None

    @pytest.mark.asyncio
    async def test_none_ttl_means_forever(self, store: ArrayStore) -> None:
        await store.put("perm", "v", ttl=None)
        assert await store.get("perm") == "v"


class TestArrayStoreMany:
    @pytest.mark.asyncio
    async def test_many_returns_all_keys(self, store: ArrayStore) -> None:
        await store.put("k1", "v1")
        await store.put("k2", "v2")
        result = await store.many(["k1", "k2", "missing"])
        assert result == {"k1": "v1", "k2": "v2", "missing": None}

    @pytest.mark.asyncio
    async def test_put_many_stores_all(self, store: ArrayStore) -> None:
        await store.put_many({"a": 1, "b": 2}, ttl=60)
        assert await store.get("a") == 1
        assert await store.get("b") == 2


class TestArrayStoreDataTypes:
    @pytest.mark.asyncio
    async def test_stores_dict(self, store: ArrayStore) -> None:
        data: dict[str, Any] = {"key": "value", "count": 42}
        await store.put("dict_key", data)
        assert await store.get("dict_key") == data

    @pytest.mark.asyncio
    async def test_stores_list(self, store: ArrayStore) -> None:
        await store.put("list_key", [1, 2, 3])
        assert await store.get("list_key") == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_stores_none_value(self, store: ArrayStore) -> None:
        await store.put("none_key", None)
        # None value stored → has() returns True, get() returns None
        assert await store.has("none_key") is True
