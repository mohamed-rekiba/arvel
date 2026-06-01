"""Tests for Session Database Store."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from arvel.session.stores.database import DatabaseSessionStore
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def store(db_engine: AsyncEngine) -> DatabaseSessionStore:
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    s = DatabaseSessionStore(session_maker=maker)
    await s.create_table(db_engine)
    return s


class TestDatabaseSessionStore:
    @pytest.mark.asyncio
    async def test_read_write_roundtrip(self, store: DatabaseSessionStore) -> None:
        await store.write("sid1", {"user_id": 99}, lifetime=120)
        data = await store.read("sid1")
        assert data["user_id"] == 99

    @pytest.mark.asyncio
    async def test_missing_session_returns_empty(self, store: DatabaseSessionStore) -> None:
        assert await store.read("nonexistent") == {}

    @pytest.mark.asyncio
    async def test_destroy_removes_session(self, store: DatabaseSessionStore) -> None:
        await store.write("sid2", {"k": "v"}, lifetime=120)
        await store.destroy("sid2")
        assert await store.read("sid2") == {}

    @pytest.mark.asyncio
    async def test_gc_removes_stale_sessions(self, store: DatabaseSessionStore) -> None:
        await store.write("old_sid", {"k": "v"}, lifetime=1)
        from sqlalchemy import text

        async with store.session_maker() as db:
            await db.execute(text("UPDATE sessions SET last_activity = 1 WHERE id = 'old_sid'"))
            await db.commit()

        deleted = await store.gc(max_lifetime=120)
        assert deleted >= 1
        assert await store.read("old_sid") == {}
