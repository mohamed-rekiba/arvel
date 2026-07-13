"""ORM depth (doc 07) — read/write connection split + sticky. Test-first."""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Item(Model):
    __fields__ = {"n": int}
    __fillable__ = ["n"]


def _split_config(db_path: Path) -> dict[str, dict[str, object]]:
    url = f"sqlite+aiosqlite:///{db_path}"
    return {"default": {"read": {"url": url}, "write": {"url": url}, "sticky": True}}


async def test_flat_config_shares_one_engine() -> None:
    db = ConnectionResolver()  # in-memory, no split — unchanged behaviour
    try:
        assert db.engine(mode="read") is db.engine(mode="write")
    finally:
        await db.dispose()


async def test_split_config_uses_distinct_engines(tmp_path: Path) -> None:
    db = ConnectionResolver(_split_config(tmp_path / "rw.db"))
    try:
        assert db.engine(mode="read") is not db.engine(mode="write")
    finally:
        await db.dispose()


async def test_sticky_routes_reads_to_writer_after_a_write(tmp_path: Path) -> None:
    db = ConnectionResolver(_split_config(tmp_path / "sticky.db"))
    try:
        writer = db.engine(mode="write")
        assert db.engine(mode="read") is not writer  # before any write → reader
        await db.execute(sa.text("CREATE TABLE marker (id integer)"))  # a write
        assert db.engine(mode="read") is writer  # sticky → reads now hit the writer
    finally:
        await db.dispose()


async def test_model_round_trips_through_split(tmp_path: Path) -> None:
    db = ConnectionResolver(_split_config(tmp_path / "model.db"))
    Item.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Item.__table__))
        await Item.create(n=7)  # write engine
        items = await Item.all()  # read engine (same file)
        assert [i.n for i in items] == [7]
    finally:
        await db.dispose()
