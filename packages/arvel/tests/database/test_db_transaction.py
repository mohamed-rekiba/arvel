"""AC-010-04..05 — DB.transaction() facade (FR-010-04)."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, id_, string
from arvel.database.db import DB
from arvel.database.session import reset_active_session, set_active_session
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class TxWidget(Model):
    __tablename__ = "tx_widgets"
    id: int = id_()
    name: str = string(80)


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def _query_rows(session_maker: async_sessionmaker[AsyncSession]) -> list[TxWidget]:
    """Open a fresh session to verify committed data."""
    async with session_maker() as s:
        token = set_active_session(s)
        try:
            rows = await TxWidget.order_by("name").all()
            return list(rows)
        finally:
            reset_active_session(token)


async def _do_rollback() -> None:
    async with DB.transaction():
        await TxWidget.create(name="should_rollback")
        raise ValueError("boom")


async def _do_nested_inner_fail() -> None:
    async with DB.transaction():
        await TxWidget.create(name="inner_rolled_back")
        raise ValueError("inner boom")


async def _do_outer_rollback() -> None:
    async with DB.transaction():
        await TxWidget.create(name="outer_rb")
        async with DB.transaction():
            await TxWidget.create(name="inner_rb")
        raise RuntimeError("outer boom")


async def _do_savepoint_rollback() -> None:
    async with DB.transaction():
        await TxWidget.create(name="inside_savepoint")
        raise ValueError("savepoint rollback")


# ─── commit path ─────────────────────────────────────────────────────────────


async def test_transaction_commits_on_success(
    engine: Any,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """AC-010-04: DB.transaction() commits on successful exit."""
    await _create_tables(engine)
    DB.configure(session_maker)

    async with DB.transaction():
        await TxWidget.create(name="committed")

    rows = await _query_rows(session_maker)
    assert len(rows) == 1
    assert rows[0].name == "committed"


# ─── rollback path ───────────────────────────────────────────────────────────


async def test_transaction_rolls_back_on_exception(
    engine: Any,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """AC-010-04: DB.transaction() rolls back on exception."""
    await _create_tables(engine)
    DB.configure(session_maker)

    with pytest.raises(ValueError):
        await _do_rollback()

    rows = await _query_rows(session_maker)
    assert len(rows) == 0


# ─── nested savepoint ────────────────────────────────────────────────────────


async def test_nested_transaction_uses_savepoint(
    engine: Any,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """AC-010-05: nested DB.transaction() creates a savepoint, not a second connection."""
    await _create_tables(engine)
    DB.configure(session_maker)

    async with DB.transaction():
        await TxWidget.create(name="outer")
        with pytest.raises(ValueError):
            await _do_nested_inner_fail()

    rows = await _query_rows(session_maker)
    names = [r.name for r in rows]
    assert "outer" in names
    assert "inner_rolled_back" not in names


async def test_nested_transaction_inner_commit_outer_rollback(
    engine: Any,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Inner savepoint commit, then outer rollback rolls back everything."""
    await _create_tables(engine)
    DB.configure(session_maker)

    with pytest.raises(RuntimeError):
        await _do_outer_rollback()

    rows = await _query_rows(session_maker)
    assert len(rows) == 0


# ─── HTTP middleware compatibility ────────────────────────────────────────────


async def test_transaction_inside_active_session_uses_savepoint(
    engine: Any,
    session: AsyncSession,
) -> None:
    """With an active session (HTTP middleware), DB.transaction() uses begin_nested()."""
    await _create_tables(engine)

    with pytest.raises(ValueError):
        await _do_savepoint_rollback()

    rows = await TxWidget.all()
    assert len(rows) == 0
