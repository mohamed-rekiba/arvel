"""Shared in-memory SQLite session helper for tests that need a simple DB.

Import ``SampleUser`` from ``tests._fixtures.models``. Use
``create_memory_session()`` to get an async generator of sessions with
rollback isolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from arvel.data.model import ArvelModel
from tests._fixtures.models import SampleUser as SampleUser

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession


async def create_memory_session() -> AsyncGenerator[AsyncSession]:
    """In-memory SQLite session with rollback isolation."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(ArvelModel.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        yield session
        await session.rollback()

    await engine.dispose()
