"""Model-factory fluent parity: the factory had make/create/make_many/create_many but lacked
state (dict or callable), sequence, raw, and the fluent count() batch. state() is immutable (returns a
copy); count() routes through FactoryBatch so make/create return lists."""

from __future__ import annotations

from typing import Any, ClassVar

import sqlalchemy as sa

from arvel import Model
from arvel.database import ConnectionResolver, Factory, FactoryBatch


class Widget(Model):
    __table_name__ = "widgets"
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "price": int, "active": bool}
    __fillable__: ClassVar[list[str]] = ["name", "price", "active"]


class WidgetFactory(Factory[Widget]):
    model = Widget

    def definition(self) -> dict[str, Any]:
        return {"name": "widget", "price": 10, "active": True}


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    Widget.set_connection(db)
    await db.execute(sa.schema.CreateTable(Widget.__table__))
    return db


def test_raw_and_make() -> None:
    f = WidgetFactory()
    assert f.raw() == {"name": "widget", "price": 10, "active": True}
    assert f.raw(name="x") == {"name": "x", "price": 10, "active": True}
    assert f.make().price == 10


def test_state_dict_and_callable_is_immutable() -> None:
    f = WidgetFactory()
    admin = f.state({"active": False})
    assert admin.make().active is False
    assert f.make().active is True  # original factory unchanged (state returns a copy)
    pricey = f.state(lambda attrs: {"price": attrs["price"] * 2})
    assert pricey.make().price == 20


async def test_count_batch_returns_list() -> None:
    db = await _db()
    try:
        batch = WidgetFactory().count(3)
        assert isinstance(batch, FactoryBatch)
        made = batch.make()
        assert isinstance(made, list) and len(made) == 3
        created = await WidgetFactory().count(2).create(name="bulk")
        assert len(created) == 2 and all(w.name == "bulk" for w in created)
    finally:
        await db.dispose()


def test_count_with_sequence_cycles() -> None:
    made = WidgetFactory().count(3).sequence({"price": 1}, {"price": 2}).make()
    assert [w.price for w in made] == [1, 2, 1]  # cycles per index


def test_count_with_state() -> None:
    made = WidgetFactory().count(2).state({"active": False}).make()
    assert [w.active for w in made] == [False, False]


async def test_single_create_still_returns_one() -> None:
    db = await _db()
    try:
        one = await WidgetFactory().create(price=99)
        assert isinstance(one, Widget)
        assert one.price == 99
    finally:
        await db.dispose()
