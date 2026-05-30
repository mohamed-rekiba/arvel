"""Real-SQL integration tests for ``DatabaseStore`` — FR-006-005.

The fast inner-loop suite in ``test_database_store.py`` runs against
in-memory SQLite. This file parametrizes the same coverage over Postgres
and MySQL containers so we catch driver-specific behaviour SQLite hides
(notably JSON column handling and the ``cache_entries.expires_at``
comparison semantics under the asyncpg / aiomysql dialects).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

import pytest
import pytest_asyncio
from arvel.cache.stores.database import CacheEntry, DatabaseStore
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


class PostgresEndpoint(Protocol):
    """Structural type for the ``postgres_endpoint`` fixture."""

    dsn_asyncpg: str


class MysqlEndpoint(Protocol):
    """Structural type for the ``mysql_endpoint`` fixture."""

    dsn_aiomysql: str


@pytest_asyncio.fixture(params=["postgres", "mysql"])
async def store(
    request: pytest.FixtureRequest,
) -> AsyncIterator[DatabaseStore]:
    """Yield a :class:`DatabaseStore` bound to a freshly-bootstrapped table."""
    if request.param == "postgres":
        endpoint: Any = request.getfixturevalue("postgres_endpoint")
        dsn: str = endpoint.dsn_asyncpg
    else:
        endpoint = request.getfixturevalue("mysql_endpoint")
        dsn = endpoint.dsn_aiomysql

    engine: AsyncEngine = create_async_engine(dsn, echo=False)
    try:
        # Drop any leftover table from a prior test run before creating fresh.
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS cache_entries"))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        store = DatabaseStore(session_maker=maker, prefix="test-int")
        await store.create_table(engine)
        yield store
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS cache_entries"))
        await engine.dispose()


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestDatabaseStoreSql:
    async def test_put_get_roundtrip(self, store: DatabaseStore) -> None:
        await store.put("k", "v")
        assert await store.get("k") == "v"

    async def test_missing_returns_default(self, store: DatabaseStore) -> None:
        assert await store.get("missing") is None

    async def test_complex_payload_preserved(self, store: DatabaseStore) -> None:
        data: dict[str, Any] = {"key": "value", "items": [1, 2, 3]}
        await store.put("complex", data)
        assert await store.get("complex") == data

    async def test_forget_and_has(self, store: DatabaseStore) -> None:
        await store.put("x", 1)
        assert await store.has("x") is True
        assert await store.forget("x") is True
        assert await store.has("x") is False

    async def test_flush_removes_all(self, store: DatabaseStore) -> None:
        await store.put("a", 1)
        await store.put("b", 2)
        await store.flush()
        assert await store.has("a") is False
        assert await store.has("b") is False

    async def test_gc_purges_expired_rows(self, store: DatabaseStore) -> None:
        await store.put("expired", "v", ttl=1)
        # Use the framework's own ORM table so SQLA quotes ``key`` correctly
        # under every dialect (it's reserved in MySQL — raw SQL fails there).
        async with store.session_maker() as session:
            await session.execute(
                update(CacheEntry).where(CacheEntry.key == "test-int:expired").values(expires_at=1)
            )
            await session.commit()
        assert await store.gc(max_lifetime=3600) >= 1
        assert await store.has("expired") is False
