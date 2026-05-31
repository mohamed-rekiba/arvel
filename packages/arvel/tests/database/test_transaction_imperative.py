"""Eloquent-parity (backlog 005, S12): imperative begin/commit/rollback + savepoints."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, id_, string
from arvel.database.db import DB
from arvel.database.session import reset_active_session, set_active_session
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class TxnRow(Model):
    __tablename__ = "txn_rows"
    id: int = id_()
    name: str = string(80)


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def _names(session_maker: async_sessionmaker[AsyncSession]) -> list[str]:
    async with session_maker() as s:
        token = set_active_session(s)
        try:
            return [r.name for r in await TxnRow.order_by("name").all()]
        finally:
            reset_active_session(token)


async def test_commit_persists(
    engine: Any, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _create_tables(engine)
    DB.configure(session_maker)

    await DB.begin_transaction()
    await TxnRow.create(name="keep")
    await DB.commit()

    assert await _names(session_maker) == ["keep"]


async def test_rollback_discards(
    engine: Any, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _create_tables(engine)
    DB.configure(session_maker)

    await DB.begin_transaction()
    await TxnRow.create(name="gone")
    await DB.rollback()

    assert await _names(session_maker) == []


async def test_nested_savepoint_rollback_keeps_outer(
    engine: Any, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _create_tables(engine)
    DB.configure(session_maker)

    await DB.begin_transaction()
    await TxnRow.create(name="outer")
    await DB.begin_transaction()  # SAVEPOINT
    await TxnRow.create(name="inner")
    await DB.rollback()  # roll back to savepoint
    await DB.commit()

    assert await _names(session_maker) == ["outer"]


async def test_nested_savepoint_commit_keeps_both(
    engine: Any, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _create_tables(engine)
    DB.configure(session_maker)

    await DB.begin_transaction()
    await TxnRow.create(name="a")
    await DB.begin_transaction()
    await TxnRow.create(name="b")
    await DB.commit()  # release savepoint
    await DB.commit()  # commit outer

    assert await _names(session_maker) == ["a", "b"]


async def test_commit_without_begin_raises(
    engine: Any, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    DB.configure(session_maker)
    with pytest.raises(RuntimeError, match="without a matching"):
        await DB.commit()


async def test_savepoint_inside_db_transaction(
    engine: Any, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _create_tables(engine)
    DB.configure(session_maker)

    async with DB.transaction():
        await TxnRow.create(name="ctx")
        await DB.begin_transaction()  # SAVEPOINT on the context-managed session
        await TxnRow.create(name="sp")
        await DB.rollback()

    assert await _names(session_maker) == ["ctx"]


async def test_after_commit_fires_on_imperative_commit(
    engine: Any, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _create_tables(engine)
    DB.configure(session_maker)
    fired: list[str] = []

    async def cb() -> None:
        fired.append("done")

    await DB.begin_transaction()
    await TxnRow.create(name="x")
    DB.after_commit(cb)
    assert fired == []
    await DB.commit()
    assert fired == ["done"]


async def test_after_commit_skipped_on_imperative_rollback(
    engine: Any, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _create_tables(engine)
    DB.configure(session_maker)
    fired: list[str] = []

    async def cb() -> None:
        fired.append("done")

    await DB.begin_transaction()
    await TxnRow.create(name="x")
    DB.after_commit(cb)
    await DB.rollback()
    assert fired == []
