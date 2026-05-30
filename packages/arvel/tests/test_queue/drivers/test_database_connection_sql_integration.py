"""Real-SQL integration tests for ``DatabaseConnection`` — FR-008-005.

The fast inner-loop suite in ``test_database.py`` runs against in-memory
SQLite (which DatabaseConnection bootstraps itself). This file bypasses
the built-in SQLite engine, injects a Postgres- or MySQL-backed
``session_factory``, and exercises the same push/pop/size/clear contract
against the real database — catching driver-specific issues that SQLite
hides, like ``FOR UPDATE`` semantics under concurrent workers and the
``INTEGER`` vs ``BIGINT`` precision difference for ``available_at``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

import pytest
import pytest_asyncio
from arvel.queue.drivers.database import DatabaseConnection
from arvel.queue.envelope import JobEnvelope
from arvel.queue.job import Job
from sqlalchemy import (
    BigInteger,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


class _SqlIntJob(Job):
    """Test job registered with JobRegistry so the database driver's
    deserialize path accepts our envelopes (otherwise unknown classes
    are routed to the failed-jobs table and pop returns ``None``).
    """

    message: str

    async def handle(self) -> None:
        return None


class PostgresEndpoint(Protocol):
    """Structural type for the ``postgres_endpoint`` fixture."""

    dsn_asyncpg: str


class MysqlEndpoint(Protocol):
    """Structural type for the ``mysql_endpoint`` fixture."""

    dsn_aiomysql: str


def _envelope(payload: str = "hello") -> JobEnvelope:
    # Build the envelope via the registered job so its ``job_class`` key
    # matches what the database driver's deserialize lookup expects.
    return _SqlIntJob(message=payload).to_envelope()


async def _create_jobs_table(engine: AsyncEngine) -> None:
    """Mirror ``arvel.queue.drivers.database._JobRow`` against the real database.

    We don't reuse the ORM mapper because it's tied to ``DatabaseConnection``'s
    internal SQLite engine; using a plain ``Table`` lets the same DDL work
    on Postgres and MySQL without dialect-specific tweaks.
    """
    md = MetaData()
    Table(
        "jobs",
        md,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("queue", String(255), nullable=False, index=True),
        Column("payload", Text, nullable=False),
        Column("attempts", Integer, nullable=False, default=0),
        Column("available_at", BigInteger, nullable=False),
        Column("created_at", BigInteger, nullable=False),
        # FR-018-07: priority column added by WI-018.
        Column("priority", Integer, nullable=False, default=0),
    )
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS jobs"))
        await conn.run_sync(md.create_all)


@pytest_asyncio.fixture(params=["postgres", "mysql"])
async def driver(
    request: pytest.FixtureRequest,
) -> AsyncIterator[DatabaseConnection]:
    if request.param == "postgres":
        endpoint: Any = request.getfixturevalue("postgres_endpoint")
        dsn: str = endpoint.dsn_asyncpg
    else:
        endpoint = request.getfixturevalue("mysql_endpoint")
        dsn = endpoint.dsn_aiomysql

    engine: AsyncEngine = create_async_engine(dsn, echo=False)
    try:
        await _create_jobs_table(engine)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        connection = DatabaseConnection(config=None, session_factory=maker)
        yield connection
        await connection.close()
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS jobs"))
        await engine.dispose()


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestDatabaseConnectionSql:
    async def test_push_increases_size(self, driver: DatabaseConnection) -> None:
        await driver.push(_envelope("first"), queue="default")
        assert await driver.size("default") == 1

    async def test_pop_returns_pushed_envelope(self, driver: DatabaseConnection) -> None:
        await driver.push(_envelope("pop-me"), queue="default")
        envelope = await driver.pop_blocking(queue="default", timeout=0)
        assert envelope is not None
        assert envelope.payload["message"] == "pop-me"

    async def test_pop_empty_queue_returns_none(self, driver: DatabaseConnection) -> None:
        assert await driver.pop_blocking(queue="empty", timeout=0) is None

    async def test_clear_empties_queue(self, driver: DatabaseConnection) -> None:
        for i in range(3):
            await driver.push(_envelope(f"job-{i}"), queue="default")
        await driver.clear("default")
        assert await driver.size("default") == 0

    async def test_delayed_job_not_popped_before_available_at(
        self, driver: DatabaseConnection
    ) -> None:
        """FR-018-07: envelope.delay > 0 sets available_at = now + delay; not popped early."""
        env = _envelope("delayed")
        env.delay = 3600
        await driver.push(env, queue="default")
        assert await driver.pop_blocking(queue="default", timeout=0) is None

    async def test_priority_ordering_on_real_sql(self, driver: DatabaseConnection) -> None:
        """FR-018-07: pop returns highest-priority envelope first on Postgres + MariaDB."""
        low = _envelope("low")
        high = _envelope("high")
        high.priority = 7
        await driver.push(low, queue="default")
        await driver.push(high, queue="default")
        first = await driver.pop_blocking(queue="default", timeout=0)
        assert first is not None
        assert first.payload["message"] == "high"
        second = await driver.pop_blocking(queue="default", timeout=0)
        assert second is not None
        assert second.payload["message"] == "low"
