"""Fixtures for arvel-auth-social tests — in-memory SQLite + APP_KEY + httpx mocks."""

from __future__ import annotations

import base64
import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from arvel.auth.models.user import User
from arvel.database.model import Model
from arvel_auth_social.models import SocialAccount
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Deterministic 32-byte key for the app encrypter so EncryptedJson round-trips.
os.environ.setdefault("APP_KEY", "base64:" + base64.b64encode(b"k" * 32).decode())

# Keep references so linters don't drop the table-registering imports.
_MODELS = (User, SocialAccount)


@pytest_asyncio.fixture()
async def async_engine() -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture()
async def async_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
