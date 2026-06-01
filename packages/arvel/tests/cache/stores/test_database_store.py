"""Tests for DatabaseStore."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from arvel.cache.stores.database import DatabaseStore
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def store(db_engine: AsyncEngine) -> DatabaseStore:
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    s = DatabaseStore(session_maker=maker, prefix="test")
    await s.create_table(db_engine)
    return s


class TestDatabaseStoreBasicOps:
    @pytest.mark.asyncio
    async def test_put_get_roundtrip(self, store: DatabaseStore) -> None:
        await store.put("k", "v")
        assert await store.get("k") == "v"

    @pytest.mark.asyncio
    async def test_missing_returns_none(self, store: DatabaseStore) -> None:
        assert await store.get("missing") is None

    @pytest.mark.asyncio
    async def test_has_present(self, store: DatabaseStore) -> None:
        await store.put("x", 1)
        assert await store.has("x") is True

    @pytest.mark.asyncio
    async def test_forget(self, store: DatabaseStore) -> None:
        await store.put("del", "v")
        await store.forget("del")
        assert await store.has("del") is False

    @pytest.mark.asyncio
    async def test_flush(self, store: DatabaseStore) -> None:
        await store.put("a", 1)
        await store.put("b", 2)
        await store.flush()
        assert await store.has("a") is False

    @pytest.mark.asyncio
    async def test_forever_stores_with_zero_expires_at(self, store: DatabaseStore) -> None:
        await store.forever("eternal", "v")
        assert await store.get("eternal") == "v"

    @pytest.mark.asyncio
    async def test_gc_removes_expired_entries(self, store: DatabaseStore) -> None:
        await store.put("expired", "v", ttl=1)
        # Manually backdate the expires_at
        from sqlalchemy import text

        async with store.session_maker() as session:
            await session.execute(
                text("UPDATE cache_entries SET expires_at = 1 WHERE key = 'test:expired'")
            )
            await session.commit()

        deleted = await store.gc(max_lifetime=3600)
        assert deleted >= 1
        assert await store.has("expired") is False
