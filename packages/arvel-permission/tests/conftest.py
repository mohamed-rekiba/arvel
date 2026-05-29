"""Async SQLite fixtures for arvel-permission integration tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from arvel_permission.models import Permission, Role
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest_asyncio.fixture()
async def async_engine() -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Role.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture()
async def async_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture()
async def editor_role(async_session: AsyncSession) -> Role:
    role = Role(name="editor", guard_name="web")
    async_session.add(role)
    await async_session.flush()
    return role


@pytest_asyncio.fixture()
async def edit_perm(async_session: AsyncSession) -> Permission:
    perm = Permission(name="edit articles", guard_name="web")
    async_session.add(perm)
    await async_session.flush()
    return perm
