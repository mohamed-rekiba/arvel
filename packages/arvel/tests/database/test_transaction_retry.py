"""Eloquent-parity: DB.transactional retry on deadlock."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, id_, string
from arvel.database.db import DB, is_retryable_db_error
from arvel.database.session import reset_active_session, set_active_session
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class RetryRow(Model):
    __tablename__ = "retry_rows"
    id: int = id_()
    name: str = string(80)


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def _query_rows(session_maker: async_sessionmaker[AsyncSession]) -> list[RetryRow]:
    async with session_maker() as s:
        token = set_active_session(s)
        try:
            return list(await RetryRow.order_by("name").all())
        finally:
            reset_active_session(token)


def _deadlock() -> OperationalError:
    return OperationalError("UPDATE ...", {}, Exception("deadlock detected"))


def test_is_retryable_predicate() -> None:
    assert is_retryable_db_error(_deadlock()) is True
    assert is_retryable_db_error(OperationalError("x", {}, Exception("database is locked")))
    serialization = OperationalError("x", {}, Exception("could not serialize access"))
    assert is_retryable_db_error(serialization) is True
    assert is_retryable_db_error(ValueError("nope")) is False
    assert is_retryable_db_error(IntegrityError("x", {}, Exception("unique"))) is False


async def test_retries_then_succeeds(
    engine: Any, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _create_tables(engine)
    DB.configure(session_maker)
    calls = 0

    async def body(session: AsyncSession) -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise _deadlock()
        await RetryRow.create(name="ok")
        return "done"

    result = await DB.transactional(body, attempts=3)
    assert result == "done"
    assert calls == 2
    assert [r.name for r in await _query_rows(session_maker)] == ["ok"]


async def test_exhausts_attempts_and_raises(
    engine: Any, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _create_tables(engine)
    DB.configure(session_maker)
    calls = 0

    async def body(session: AsyncSession) -> None:
        nonlocal calls
        calls += 1
        raise _deadlock()

    with pytest.raises(OperationalError):
        await DB.transactional(body, attempts=2)
    assert calls == 2


async def test_non_retryable_propagates_immediately(
    engine: Any, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _create_tables(engine)
    DB.configure(session_maker)
    calls = 0

    async def body(session: AsyncSession) -> None:
        nonlocal calls
        calls += 1
        raise ValueError("logic error")

    with pytest.raises(ValueError, match="logic error"):
        await DB.transactional(body, attempts=3)
    assert calls == 1


async def test_returns_value_single_attempt(
    engine: Any, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _create_tables(engine)
    DB.configure(session_maker)
    calls = 0

    async def body(session: AsyncSession) -> int:
        nonlocal calls
        calls += 1
        return 42

    assert await DB.transactional(body) == 42
    assert calls == 1


async def test_failed_attempt_rolls_back_before_retry(
    engine: Any, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _create_tables(engine)
    DB.configure(session_maker)
    calls = 0

    async def body(session: AsyncSession) -> str:
        nonlocal calls
        calls += 1
        await RetryRow.create(name=f"attempt{calls}")
        if calls < 2:
            raise _deadlock()
        return "ok"

    await DB.transactional(body, attempts=3)
    # The first attempt's insert must have rolled back — only the winning row remains.
    assert [r.name for r in await _query_rows(session_maker)] == ["attempt2"]
