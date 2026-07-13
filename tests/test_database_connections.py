"""T5.1 — ConnectionResolver: async engines + Core statement execution."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver

_md = sa.MetaData()
items = sa.Table(
    "items",
    _md,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String),
)


async def test_execute_insert_and_fetch_roundtrip() -> None:
    db = ConnectionResolver()
    try:
        await db.execute(sa.schema.CreateTable(items))
        result = await db.execute(sa.insert(items).values(name="alpha"))
        assert result.rowcount == 1
        assert result.primary_key == 1

        rows = await db.fetch_all(sa.select(items))
        assert [r["name"] for r in rows] == ["alpha"]

        one = await db.fetch_one(sa.select(items).where(items.c.id == 1))
        assert one is not None
        assert one["name"] == "alpha"
    finally:
        await db.dispose()


async def test_fetch_one_returns_none_when_empty() -> None:
    db = ConnectionResolver()
    try:
        await db.execute(sa.schema.CreateTable(items))
        assert await db.fetch_one(sa.select(items)) is None
    finally:
        await db.dispose()


async def test_transaction_context_commits() -> None:
    db = ConnectionResolver()
    try:
        await db.execute(sa.schema.CreateTable(items))
        async with db.transaction() as conn:
            await conn.execute(sa.insert(items).values(name="beta"))
        rows = await db.fetch_all(sa.select(items))
        assert [r["name"] for r in rows] == ["beta"]
    finally:
        await db.dispose()
