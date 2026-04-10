"""Shared fixtures for activity tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests._fixtures.database import SampleUser, create_memory_session

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["SampleUser"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    async for session in create_memory_session():
        yield session
