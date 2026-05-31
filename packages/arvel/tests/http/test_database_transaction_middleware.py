"""ADR-016 — DatabaseTransaction middleware (sanctioned http↔db bridge)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from arvel.database import Model, id_, string
from arvel.database.session import get_active_session
from arvel.http.middleware.database_transaction import DatabaseTransaction
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class TxModel(Model):
    __tablename__ = "tx_models"
    id: int = id_()
    label: str = string(80)


@pytest_asyncio.fixture
async def tx_session_maker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


class _DummyRequest:
    pass


class _Response:
    def __init__(self, status_code: object = 200) -> None:
        self.status_code = status_code


async def test_middleware_binds_session_for_handler(
    tx_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    mw = DatabaseTransaction(session_maker=tx_session_maker)
    sessions_seen: list[AsyncSession] = []

    async def handler(_: Any) -> _Response:
        sessions_seen.append(get_active_session())
        return _Response(200)

    resp = await mw.handle(_DummyRequest(), handler)
    assert resp.status_code == 200
    assert len(sessions_seen) == 1


async def test_middleware_commits_on_success(
    tx_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    mw = DatabaseTransaction(session_maker=tx_session_maker)

    async def handler(_: Any) -> _Response:
        await TxModel.create(label="committed")
        return _Response(200)

    await mw.handle(_DummyRequest(), handler)

    # New session — re-read.
    async with tx_session_maker() as s:
        from arvel.database.session import use_session

        async with use_session(s):
            rows = await TxModel.all()
            assert any(r.label == "committed" for r in rows)


async def test_middleware_rolls_back_on_handler_exception(
    tx_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    mw = DatabaseTransaction(session_maker=tx_session_maker)

    class BoomError(Exception):
        pass

    async def handler(_: Any) -> _Response:
        await TxModel.create(label="should-roll-back")
        raise BoomError

    with pytest.raises(BoomError):
        await mw.handle(_DummyRequest(), handler)

    async with tx_session_maker() as s:
        from arvel.database.session import use_session

        async with use_session(s):
            rows = await TxModel.all()
            assert not any(r.label == "should-roll-back" for r in rows)


async def test_middleware_rolls_back_on_4xx_response(
    tx_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    mw = DatabaseTransaction(session_maker=tx_session_maker)

    async def handler(_: Any) -> _Response:
        await TxModel.create(label="error-path")
        return _Response(400)

    resp = await mw.handle(_DummyRequest(), handler)
    assert resp.status_code == 400

    async with tx_session_maker() as s:
        from arvel.database.session import use_session

        async with use_session(s):
            rows = await TxModel.all()
            assert not any(r.label == "error-path" for r in rows)


async def test_middleware_resolves_session_maker_from_container(
    tx_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    class _Container:
        def make(self, key: object) -> async_sessionmaker[AsyncSession]:
            assert key == async_sessionmaker[AsyncSession]
            return tx_session_maker

    mw = DatabaseTransaction()
    state = SimpleNamespace(arvel_container=_Container())
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    sessions_seen: list[AsyncSession] = []

    async def handler(_: object) -> _Response:
        sessions_seen.append(get_active_session())
        return _Response(200)

    resp = await mw.handle(request, handler)

    assert resp.status_code == 200
    assert len(sessions_seen) == 1


async def test_middleware_raises_without_container() -> None:
    mw = DatabaseTransaction()

    async def handler(_: object) -> _Response:
        return _Response(200)

    with pytest.raises(RuntimeError, match="arvel_container"):
        await mw.handle(_DummyRequest(), handler)


async def test_middleware_commits_when_status_code_is_not_numeric(
    tx_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    mw = DatabaseTransaction(session_maker=tx_session_maker)

    async def handler(_: object) -> _Response:
        await TxModel.create(label="non-numeric-status")
        return _Response("not-a-status")

    resp = await mw.handle(_DummyRequest(), handler)
    assert resp.status_code == "not-a-status"

    async with tx_session_maker() as s:
        from arvel.database.session import use_session

        async with use_session(s):
            rows = await TxModel.all()
            assert any(r.label == "non-numeric-status" for r in rows)


async def test_middleware_rolls_back_on_5xx_response(
    tx_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    mw = DatabaseTransaction(session_maker=tx_session_maker)

    async def handler(_: object) -> _Response:
        await TxModel.create(label="server-error-path")
        return _Response(500)

    resp = await mw.handle(_DummyRequest(), handler)
    assert resp.status_code == 500

    async with tx_session_maker() as s:
        from arvel.database.session import use_session

        async with use_session(s):
            rows = await TxModel.all()
            assert not any(r.label == "server-error-path" for r in rows)
