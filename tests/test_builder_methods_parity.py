"""Query-builder parity (Laravel): common methods that were entirely absent — where_not_in /
where_between / where_not_between / or_where_in, the `when` conditional clause, skip/take aliases,
pluck / value, and first_or_fail. A real app reaches for these constantly."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
import sqlalchemy as sa

from arvel import Model
from arvel.database import ConnectionResolver
from arvel.database.model import ModelNotFound


class Item(Model):
    __table_name__ = "items"
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "price": int, "tag": str}
    __fillable__: ClassVar[list[str]] = ["name", "price", "tag"]


async def _seed() -> ConnectionResolver:
    db = ConnectionResolver()
    Item.set_connection(db)
    await db.execute(sa.schema.CreateTable(Item.__table__))
    for name, price, tag in [("a", 10, "x"), ("b", 20, "y"), ("c", 30, "x"), ("d", 40, "z")]:
        await Item.create(name=name, price=price, tag=tag)
    return db


async def test_where_variants() -> None:
    db = await _seed()
    try:
        assert sorted(i.name for i in await Item.query().where_not_in("tag", ["x"]).get()) == [
            "b",
            "d",
        ]
        assert sorted(
            i.name for i in await Item.query().where_between("price", [15, 35]).get()
        ) == [
            "b",
            "c",
        ]
        assert sorted(
            i.name for i in await Item.query().where_not_between("price", [15, 35]).get()
        ) == ["a", "d"]
        got = await Item.query().where("tag", "=", "y").or_where_in("tag", ["z"]).get()
        assert sorted(i.name for i in got) == ["b", "d"]
    finally:
        await db.dispose()


async def test_when_conditional_clause() -> None:
    db = await _seed()
    try:
        applied = await Item.query().when(True, lambda q: q.where("tag", "=", "x")).get()
        assert sorted(i.name for i in applied) == ["a", "c"]
        skipped = await Item.query().when(False, lambda q: q.where("tag", "=", "x")).get()
        assert len(skipped) == 4
        defaulted = (
            await Item.query()
            .when(False, lambda q: q.where("tag", "=", "x"), lambda q: q.where("tag", "=", "z"))
            .get()
        )
        assert [i.name for i in defaulted] == ["d"]
    finally:
        await db.dispose()


async def test_skip_take_aliases() -> None:
    db = await _seed()
    try:
        rows = await Item.query().order_by("price", "asc").skip(1).take(2).get()
        assert [i.name for i in rows] == ["b", "c"]
    finally:
        await db.dispose()


async def test_pluck_and_value() -> None:
    db = await _seed()
    try:
        assert await Item.query().order_by("price", "asc").pluck("name") == ["a", "b", "c", "d"]
        assert await Item.query().pluck("price", key="name") == {"a": 10, "b": 20, "c": 30, "d": 40}
        assert await Item.query().order_by("price", "asc").value("name") == "a"
        assert await Item.query().where("tag", "=", "nope").value("name") is None
    finally:
        await db.dispose()


async def test_first_or_fail() -> None:
    db = await _seed()
    try:
        assert (await Item.query().where("tag", "=", "z").first_or_fail()).name == "d"
        with pytest.raises(ModelNotFound):
            await Item.query().where("tag", "=", "nope").first_or_fail()
    finally:
        await db.dispose()
