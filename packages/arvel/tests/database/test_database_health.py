"""Unit tests for arvel.database.health pre-flight checks."""

from __future__ import annotations

import asyncio
from typing import Self, cast

import pytest
from arvel.database import health
from arvel.database.health import (
    DatabaseUnavailableError,
    check_database_connection,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


async def test_check_connection_passes_for_reachable_engine() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        await check_database_connection(engine)
    finally:
        await engine.dispose()


async def test_check_connection_raises_when_unreachable() -> None:
    engine = create_async_engine("sqlite+aiosqlite:////nonexistent-arvel-dir/x.db")
    try:
        with pytest.raises(DatabaseUnavailableError, match="cannot connect"):
            await check_database_connection(engine)
    finally:
        await engine.dispose()


async def test_check_connection_raises_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A connect that outlives the timeout surfaces a clear 'did not respond' error."""
    monkeypatch.setattr(health, "_DEFAULT_TIMEOUT_SECONDS", 0.01)

    class _SlowConn:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_: object) -> bool:
            return False

        async def execute(self, *_: object) -> None:
            await asyncio.sleep(1)

    class _SlowEngine:
        def connect(self) -> _SlowConn:
            return _SlowConn()

    engine = cast("AsyncEngine", _SlowEngine())
    with pytest.raises(DatabaseUnavailableError, match="did not respond"):
        await check_database_connection(engine)
