"""Tests for NullStore."""

from __future__ import annotations

import pytest
from arvel.cache.stores.null import NullStore


@pytest.fixture
def store() -> NullStore:
    return NullStore()


class TestNullStore:
    @pytest.mark.asyncio
    async def test_get_always_returns_none(self, store: NullStore) -> None:
        await store.put("k", "v")
        assert await store.get("k") is None

    @pytest.mark.asyncio
    async def test_has_always_false(self, store: NullStore) -> None:
        await store.put("x", 1)
        assert await store.has("x") is False

    @pytest.mark.asyncio
    async def test_forget_returns_false(self, store: NullStore) -> None:
        assert await store.forget("k") is False

    @pytest.mark.asyncio
    async def test_flush_is_noop(self, store: NullStore) -> None:
        await store.flush()  # must not raise

    @pytest.mark.asyncio
    async def test_forever_is_noop(self, store: NullStore) -> None:
        await store.forever("k", "v")
        assert await store.get("k") is None

    @pytest.mark.asyncio
    async def test_many_returns_all_none(self, store: NullStore) -> None:
        result = await store.many(["a", "b"])
        assert result == {"a": None, "b": None}
