"""Tests for DatabaseChannel — FR-009-026, NFR-009-007."""

from __future__ import annotations

import json

import pytest

from test_notifications.helpers import (  # type: ignore[import-not-found]
    FakeUser,
    WelcomeNotification,
)


class TestDatabaseChannel:
    @pytest.mark.asyncio
    async def test_inserts_notification_row(self) -> None:
        from arvel.database.model import Model
        from arvel.notifications.channels.database_channel import DatabaseChannel
        from arvel.notifications.models.database_notification import DatabaseNotification
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Model.metadata.create_all)

            session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )

            channel = DatabaseChannel(session_factory=session_factory)
            user = FakeUser(42)
            notification = WelcomeNotification()
            await channel.send(user, notification)

            async with session_factory() as session:
                from sqlalchemy import select

                rows = (await session.execute(select(DatabaseNotification))).scalars().all()
        finally:
            await engine.dispose()

        assert len(rows) == 1
        row = rows[0]
        assert row.notifiable_id == "42"
        assert row.notifiable_type == "FakeUser"
        data = json.loads(row.data)
        assert data["action"] == "welcome"
        assert row.read_at is None

    @pytest.mark.asyncio
    async def test_data_field_truncated_to_65535_chars(self) -> None:
        """NFR-009-007: data capped at 65535 chars."""
        from typing import Any

        from arvel.notifications.channels.database_channel import DatabaseChannel
        from arvel.notifications.notification import Notification
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        class HugeDataNotification(Notification):
            def via(self, notifiable: object) -> list[str]:
                return ["database"]

            def to_database(self, notifiable: Any) -> dict[str, Any]:
                return {"data": "x" * 100_000}

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        from arvel.database.model import Model
        from arvel.notifications.models.database_notification import DatabaseNotification

        try:
            async with engine.begin() as conn:
                await conn.run_sync(Model.metadata.create_all)

            session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            channel = DatabaseChannel(session_factory=session_factory)
            await channel.send(FakeUser(1), HugeDataNotification())

            async with session_factory() as session:
                from sqlalchemy import select

                row = (await session.execute(select(DatabaseNotification))).scalars().first()
        finally:
            await engine.dispose()

        assert row is not None
        assert len(row.data) <= 65_535
