"""ORM (doc 07) — chunk_by_id + replicate + get_dirty. Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Row(Model):
    __fields__ = {"n": int, "label": str}
    __fillable__ = ["n", "label"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    Row.set_connection(db)
    await db.execute(sa.schema.CreateTable(Row.__table__))
    return db


async def test_chunk_by_id_pages_through_all_rows() -> None:
    db = await _setup()
    try:
        for i in range(1, 11):  # 10 rows
            await Row.create(n=i, label="x")
        chunks: list[list[int]] = []

        async def handle(chunk: list[Row]) -> None:
            chunks.append([r.n for r in chunk])

        await Row.chunk_by_id(4, handle)
        assert [len(c) for c in chunks] == [4, 4, 2]  # 10 rows in pages of 4
        assert sorted(n for c in chunks for n in c) == list(range(1, 11))
    finally:
        await db.dispose()


async def test_replicate_drops_pk_and_marks_unsaved() -> None:
    db = await _setup()
    try:
        original = await Row.create(n=7, label="orig")
        clone = original.replicate()
        assert clone._attributes.get("id") is None  # no primary key copied
        assert clone.n == 7
        assert clone.label == "orig"
        assert clone._exists is False
    finally:
        await db.dispose()


async def test_get_dirty_returns_changed_attributes() -> None:
    db = await _setup()
    try:
        row = await Row.create(n=1, label="before")
        assert row.get_dirty() == {}  # freshly persisted → clean
        row.label = "after"
        assert row.get_dirty() == {"label": "after"}  # only the changed field
        assert row.is_dirty() is True
    finally:
        await db.dispose()
