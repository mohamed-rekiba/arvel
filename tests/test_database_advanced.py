"""C3d — advanced DB: transactions (callback), raw SQL, pessimistic locking."""

from __future__ import annotations

import contextlib

import sqlalchemy as sa

from arvel.database import Builder, ConnectionResolver, raw

_md = sa.MetaData()
accounts = sa.Table(
    "accounts",
    _md,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("balance", sa.Integer),
)


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    await db.execute(sa.schema.CreateTable(accounts))
    await Builder(accounts, db).insert({"balance": 100})
    return db


async def test_transact_commits() -> None:
    db = await _setup()
    try:

        async def transfer(conn: object) -> None:
            await conn.execute(sa.update(accounts).values(balance=200))  # type: ignore[attr-defined]

        await db.transact(transfer)
        row = await Builder(accounts, db).first()
        assert row["balance"] == 200
    finally:
        await db.dispose()


async def test_transact_rolls_back_on_error() -> None:
    db = await _setup()
    try:

        async def boom(conn: object) -> None:
            await conn.execute(sa.update(accounts).values(balance=999))  # type: ignore[attr-defined]
            raise RuntimeError("fail")

        with contextlib.suppress(RuntimeError):
            await db.transact(boom)
        row = await Builder(accounts, db).first()
        assert row["balance"] == 100  # rolled back
    finally:
        await db.dispose()


async def test_raw_select() -> None:
    db = await _setup()
    try:
        rows = await db.select("SELECT balance FROM accounts WHERE id = :id", {"id": 1})
        assert rows[0]["balance"] == 100
    finally:
        await db.dispose()


def test_raw_is_core_text() -> None:
    expr = raw("count(*) AS n")
    assert isinstance(expr, sa.TextClause)


def test_lock_for_update_compiles() -> None:
    # SQLite ignores FOR UPDATE but the Core construct must compile for Postgres.
    from sqlalchemy.dialects import postgresql

    stmt = Builder(accounts).where(id=1).lock_for_update().to_select()
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in compiled.upper()
