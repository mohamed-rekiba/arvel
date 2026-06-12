"""Real-SQL integration tests for ``DatabaseSessionStore``

The fast inner-loop suite in ``test_database_store.py`` runs against
in-memory SQLite. This file parametrizes the same coverage over Postgres
and MySQL containers so we catch driver-specific quirks (notably TEXT
column truncation on payload, and the ``last_activity`` comparison
semantics that ``gc()`` relies on).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any, Protocol

import pytest
import pytest_asyncio
from arvel.session.stores.database import DatabaseSessionStore
from sqlalchemy import text
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
) -> AsyncIterator[DatabaseSessionStore]:
    if request.param == "postgres":
        endpoint: Any = request.getfixturevalue("postgres_endpoint")
        dsn: str = endpoint.dsn_asyncpg
    else:
        endpoint = request.getfixturevalue("mysql_endpoint")
        dsn = endpoint.dsn_aiomysql

    engine: AsyncEngine = create_async_engine(dsn, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS sessions"))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        store = DatabaseSessionStore(session_maker=maker)
        await store.create_table(engine)
        yield store
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS sessions"))
        await engine.dispose()


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestDatabaseSessionStoreSql:
    async def test_read_write_roundtrip(self, store: DatabaseSessionStore) -> None:
        await store.write("sid1", {"user_id": 1, "flash": "ok"})
        data = await store.read("sid1")
        assert data == {"user_id": 1, "flash": "ok"}

    async def test_missing_session_returns_empty(self, store: DatabaseSessionStore) -> None:
        assert await store.read("nonexistent") == {}

    async def test_write_updates_existing_row(self, store: DatabaseSessionStore) -> None:
        await store.write("sid-update", {"v": 1})
        await store.write("sid-update", {"v": 2})
        assert (await store.read("sid-update"))["v"] == 2

    async def test_destroy_removes_session(self, store: DatabaseSessionStore) -> None:
        await store.write("sid-del", {"k": "v"})
        await store.destroy("sid-del")
        assert await store.read("sid-del") == {}

    async def test_gc_purges_stale_rows(self, store: DatabaseSessionStore) -> None:
        await store.write("sid-stale", {"k": "v"})
        # Backdate the row by an hour so gc(max_lifetime=10) sees it as stale.
        async with store.session_maker() as session:
            await session.execute(
                text("UPDATE sessions SET last_activity = :ts WHERE id = 'sid-stale'").bindparams(
                    ts=int(time.time()) - 3600
                )
            )
            await session.commit()
        assert await store.gc(max_lifetime=10) >= 1
        assert await store.read("sid-stale") == {}
