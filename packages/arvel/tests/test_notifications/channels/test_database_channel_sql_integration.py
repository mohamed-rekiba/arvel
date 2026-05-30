"""Real-SQL integration tests for ``DatabaseChannel`` — FR-009-026.

Parametrizes the notification database channel over Postgres and MySQL
containers. The channel writes through a ``Notification``-derived row using
the framework's ``DatabaseNotification`` model, so this also exercises the
SQLAlchemy ``DateTime(timezone=True)`` and ``Text`` columns under both
dialects — areas where SQLite silently smooths over real differences.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Protocol, cast

import pytest
import pytest_asyncio
from arvel.notifications.channels.database_channel import DatabaseChannel
from arvel.notifications.models.database_notification import DatabaseNotification
from arvel.notifications.notification import Notification
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


class PostgresEndpoint(Protocol):
    """Structural type for the ``postgres_endpoint`` fixture."""

    dsn_asyncpg: str


class MysqlEndpoint(Protocol):
    """Structural type for the ``mysql_endpoint`` fixture."""

    dsn_aiomysql: str


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _WelcomeNotification(Notification):
    def via(self, notifiable: Any) -> list[str]:
        return ["database"]

    def to_database(self, notifiable: Any) -> dict[str, Any]:
        notifiable_id = cast("int", getattr(notifiable, "id", 0))
        return {"action": "welcome", "user_id": notifiable_id}


@pytest_asyncio.fixture(params=["postgres", "mysql"])
async def channel(
    request: pytest.FixtureRequest,
) -> AsyncIterator[tuple[DatabaseChannel, async_sessionmaker[Any]]]:
    if request.param == "postgres":
        endpoint: Any = request.getfixturevalue("postgres_endpoint")
        dsn: str = endpoint.dsn_asyncpg
    else:
        endpoint = request.getfixturevalue("mysql_endpoint")
        dsn = endpoint.dsn_aiomysql

    engine: AsyncEngine = create_async_engine(dsn, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS notifications"))
            await conn.run_sync(DatabaseNotification.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        yield DatabaseChannel(maker), maker
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS notifications"))
        await engine.dispose()


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestDatabaseChannelSql:
    async def test_send_inserts_notification_row(
        self,
        channel: tuple[DatabaseChannel, async_sessionmaker[Any]],
    ) -> None:
        chan, maker = channel
        await chan.send(_FakeUser(42), _WelcomeNotification())
        async with maker() as session:
            rows = (await session.execute(select(DatabaseNotification))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.notifiable_id == "42"
        assert row.notifiable_type == "_FakeUser"
        payload = json.loads(row.data)
        assert payload == {"action": "welcome", "user_id": 42}
        assert isinstance(row.created_at, datetime)
        assert row.read_at is None

    async def test_multiple_sends_create_multiple_rows(
        self,
        channel: tuple[DatabaseChannel, async_sessionmaker[Any]],
    ) -> None:
        chan, maker = channel
        for i in range(3):
            await chan.send(_FakeUser(i), _WelcomeNotification())
        async with maker() as session:
            rows = (await session.execute(select(DatabaseNotification))).scalars().all()
        assert len(rows) == 3
        ids = sorted(r.notifiable_id for r in rows)
        assert ids == ["0", "1", "2"]
