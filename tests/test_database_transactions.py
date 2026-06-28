"""Advanced DB (doc 08) — nested transactions (savepoints) + retry. Test-first."""

from __future__ import annotations

import contextlib

import sqlalchemy as sa

from arvel.database import Builder, ConnectionResolver

_md = sa.MetaData()
accounts = sa.Table(
    "accounts", _md, sa.Column("id", sa.Integer, primary_key=True), sa.Column("balance", sa.Integer)
)


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    await db.execute(sa.schema.CreateTable(accounts))
    await Builder(accounts, db).insert({"balance": 100})
    return db


async def test_nested_transaction_inner_rollback_keeps_outer() -> None:
    db = await _db()
    try:
        async with db.transaction() as conn:
            await conn.execute(sa.update(accounts).values(balance=200))
            with contextlib.suppress(RuntimeError):
                async with db.transaction() as inner:  # savepoint
                    await inner.execute(sa.update(accounts).values(balance=999))
                    raise RuntimeError("roll back the savepoint only")
        row = await Builder(accounts, db).first()
        assert row["balance"] == 200  # outer committed, inner savepoint rolled back
    finally:
        await db.dispose()


async def test_nested_transaction_both_commit() -> None:
    db = await _db()
    try:
        async with db.transaction() as conn:
            await conn.execute(sa.update(accounts).values(balance=200))
            async with db.transaction() as inner:
                await inner.execute(sa.update(accounts).values(balance=300))
        row = await Builder(accounts, db).first()
        assert row["balance"] == 300
    finally:
        await db.dispose()


async def test_transact_retries_on_transient_error() -> None:
    db = await _db()
    try:
        calls = {"n": 0}

        async def work(conn: sa.Connection) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                from sqlalchemy.exc import OperationalError

                raise OperationalError("stmt", {}, Exception("deadlock detected"))
            await conn.execute(sa.update(accounts).values(balance=500))

        await db.transact(work, attempts=3)
        assert calls["n"] == 2  # retried once, then succeeded
        row = await Builder(accounts, db).first()
        assert row["balance"] == 500
    finally:
        await db.dispose()
