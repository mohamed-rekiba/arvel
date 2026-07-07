"""Raw SQL + streaming must run on the enclosing transaction's connection —
they see uncommitted writes and roll back with the transaction."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver


async def _setup(db: ConnectionResolver) -> None:
    await db.execute(
        sa.text("CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    )


async def test_raw_select_sees_uncommitted_writes_inside_transaction() -> None:
    db = ConnectionResolver()
    try:
        await _setup(db)
        async with db.transaction():
            await db.statement("INSERT INTO items (name) VALUES (:n)", {"n": "draft"})
            rows = await db.select("SELECT name FROM items")
            assert [r["name"] for r in rows] == ["draft"]  # same connection → visible
    finally:
        await db.dispose()


async def test_raw_statement_rolls_back_with_enclosing_transaction() -> None:
    db = ConnectionResolver()
    try:
        await _setup(db)
        try:
            async with db.transaction():
                await db.statement("INSERT INTO items (name) VALUES (:n)", {"n": "doomed"})
                raise RuntimeError("abort")
        except RuntimeError:
            pass
        rows = await db.select("SELECT name FROM items")
        assert rows == []  # the raw write must not escape the rollback
    finally:
        await db.dispose()


async def test_stream_reads_from_transaction_connection() -> None:
    db = ConnectionResolver()
    try:
        await _setup(db)
        async with db.transaction():
            await db.statement("INSERT INTO items (name) VALUES (:n)", {"n": "streamed"})
            seen = [row["name"] async for row in db.stream(sa.text("SELECT name FROM items"))]
            assert seen == ["streamed"]
    finally:
        await db.dispose()


async def test_raw_select_outside_transaction_unchanged() -> None:
    db = ConnectionResolver()
    try:
        await _setup(db)
        await db.statement("INSERT INTO items (name) VALUES (:n)", {"n": "kept"})
        rows = await db.select("SELECT name FROM items WHERE name = :n", {"n": "kept"})
        assert [r["name"] for r in rows] == ["kept"]
    finally:
        await db.dispose()
