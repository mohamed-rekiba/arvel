"""Eloquent-parity (backlog 005, S11): debugging + query-log parity.

to_raw_sql, get_bindings, explain, DB.enable_query_log/get_query_log, DB.pretend.
"""

from __future__ import annotations

from arvel.database import Model, id_, integer, string
from arvel.database.db import DB
from arvel.database.session import reset_active_session, set_active_session
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


class DbgItem(Model):
    __tablename__ = "dbg_items"
    id: int = id_()
    name: str = string(80)
    score: int = integer(default=0)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_to_raw_sql_inlines_bindings(engine: AsyncEngine, session: AsyncSession) -> None:
    sql = DbgItem.where(DbgItem.name == "abc").to_raw_sql()
    assert "abc" in sql


async def test_get_bindings_returns_values(engine: AsyncEngine, session: AsyncSession) -> None:
    binds = DbgItem.where(DbgItem.score >= 5).get_bindings()
    assert 5 in binds


async def test_explain_returns_plan_rows(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await DbgItem.create(name="x", score=1)
    plan = await DbgItem.where(DbgItem.score >= 0).explain()
    assert isinstance(plan, list)
    assert len(plan) >= 1


async def test_query_log_captures_sql_bindings_time(
    engine: AsyncEngine, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _setup(engine)
    DB.configure(session_maker)
    DB.configure_engine(engine)
    DB.enable_query_log()
    try:
        async with session_maker() as s:
            token = set_active_session(s)
            try:
                await DbgItem.create(name="x", score=1)
                await DbgItem.where(DbgItem.score >= 0).all()
            finally:
                reset_active_session(token)
        log = DB.get_query_log()
        assert len(log) >= 1
        entry = log[-1]
        assert set(entry.keys()) == {"sql", "bindings", "time_ms"}
        assert isinstance(entry["sql"], str)
        assert isinstance(entry["time_ms"], float)
    finally:
        DB.disable_query_log()


async def test_flush_query_log_clears_without_disabling(
    engine: AsyncEngine, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _setup(engine)
    DB.configure(session_maker)
    DB.configure_engine(engine)
    DB.enable_query_log()
    try:
        async with session_maker() as s:
            token = set_active_session(s)
            try:
                await DbgItem.create(name="y", score=2)
            finally:
                reset_active_session(token)
        assert len(DB.get_query_log()) >= 1
        DB.flush_query_log()
        assert DB.get_query_log() == []
    finally:
        DB.disable_query_log()


async def test_pretend_records_but_does_not_persist(
    engine: AsyncEngine, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    await _setup(engine)
    DB.configure(session_maker)
    DB.configure_engine(engine)

    async def writes() -> None:
        await DbgItem.create(name="ghost", score=99)

    log = await DB.pretend(writes)

    assert any("INSERT" in entry["sql"].upper() for entry in log)
    async with session_maker() as s:
        token = set_active_session(s)
        try:
            assert await DbgItem.where(DbgItem.name == "ghost").count() == 0
        finally:
            reset_active_session(token)
