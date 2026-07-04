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


def test_query_entry_classmethods_return_a_typed_builder() -> None:
    """The common query starters are explicit typed classmethods (return Builder), not just the
    metaclass Any-proxy — so `Model.where(...).first()` is strict-type-safe without `.query()`."""
    from arvel.database.builder import Builder

    for builder in (
        Item.where("tag", "x"),
        Item.or_where("tag", "x"),
        Item.where_in("tag", ["x"]),
        Item.where_not_in("tag", ["x"]),
        Item.with_(),
        Item.order_by("price"),
    ):
        assert isinstance(builder, Builder)
    # `when` is intentionally not a Model classmethod — it would shadow a column named `when`
    assert isinstance(Item.query().when(True, lambda q: q), Builder)


async def test_where_variants() -> None:
    db = await _seed()
    try:
        assert sorted(i.name for i in await Item.where_not_in("tag", ["x"]).get()) == [
            "b",
            "d",
        ]
        assert sorted(i.name for i in await Item.where_between("price", [15, 35]).get()) == [
            "b",
            "c",
        ]
        assert sorted(i.name for i in await Item.where_not_between("price", [15, 35]).get()) == [
            "a",
            "d",
        ]
        got = await Item.where("tag", "=", "y").or_where_in("tag", ["z"]).get()
        assert sorted(i.name for i in got) == ["b", "d"]
    finally:
        await db.dispose()


async def test_when_conditional_clause() -> None:
    db = await _seed()
    try:
        applied = await Item.when(True, lambda q: q.where("tag", "=", "x")).get()
        assert sorted(i.name for i in applied) == ["a", "c"]
        skipped = await Item.when(False, lambda q: q.where("tag", "=", "x")).get()
        assert len(skipped) == 4
        defaulted = (
            await Item.query()
            .when(False, lambda q: q.where("tag", "=", "x"), lambda q: q.where("tag", "=", "z"))
            .get()
        )
        assert [i.name for i in defaulted] == ["d"]
    finally:
        await db.dispose()


async def test_when_passes_value_laravel_style() -> None:
    """Laravel parity: ``when($value, fn($query, $value))`` passes the truthy value as the
    callback's second argument. A 1-arg callback (close-over style) must keep working."""
    db = await _seed()
    try:
        # 2-arg callback receives the value (here the tag to filter on)
        got = await Item.when("x", lambda q, value: q.where("tag", "=", value)).get()
        assert sorted(i.name for i in got) == ["a", "c"]
        # the default branch also receives the (falsy) value as its 2nd arg
        defaulted = (
            await Item.query()
            .when(
                "",
                lambda q, value: q.where("tag", "=", "x"),
                lambda q, value: q.where("tag", "=", "z"),
            )
            .get()
        )
        assert [i.name for i in defaulted] == ["d"]
        # 1-arg callback (existing style) still works
        one_arg = await Item.when(True, lambda q: q.where("tag", "=", "y")).get()
        assert [i.name for i in one_arg] == ["b"]
    finally:
        await db.dispose()


async def test_when_unless_edge_callbacks() -> None:
    """Edge forms: a ``*args`` callback receives the value; a falsy ``when`` / truthy ``unless``
    with no default is a no-op that returns the builder unchanged (chainable)."""
    db = await _seed()
    try:
        # *args callback → the value is passed through as the 2nd positional
        got = await Item.when("z", lambda *a: a[0].where("tag", "=", a[1])).get()
        assert [i.name for i in got] == ["d"]
        # falsy when, no default → no clause added (all rows)
        none_added = await Item.when(False, lambda q: q.where("tag", "=", "x")).get()
        assert len(none_added) == 4
        # truthy unless, no default → no clause added (all rows)
        unless_noop = await Item.unless(True, lambda q: q.where("tag", "=", "x")).get()
        assert len(unless_noop) == 4
    finally:
        await db.dispose()


async def test_unless_conditional_clause() -> None:
    """Laravel ``unless`` — the inverse of ``when`` (applies the callback when the condition is
    falsy), with the same value-passing + default-branch semantics."""
    db = await _seed()
    try:
        # condition falsy → callback applies; value passed through
        applied = await Item.unless(False, lambda q, value: q.where("tag", "=", "x")).get()
        assert sorted(i.name for i in applied) == ["a", "c"]
        # condition truthy → callback skipped, default (if any) applies
        defaulted = (
            await Item.query()
            .unless("on", lambda q: q.where("tag", "=", "x"), lambda q: q.where("tag", "=", "z"))
            .get()
        )
        assert [i.name for i in defaulted] == ["d"]
    finally:
        await db.dispose()


async def test_skip_take_aliases() -> None:
    db = await _seed()
    try:
        rows = await Item.order_by("price", "asc").skip(1).take(2).get()
        assert [i.name for i in rows] == ["b", "c"]
    finally:
        await db.dispose()


async def test_pluck_and_value() -> None:
    db = await _seed()
    try:
        assert await Item.order_by("price", "asc").pluck("name") == ["a", "b", "c", "d"]
        assert await Item.pluck("price", key="name") == {"a": 10, "b": 20, "c": 30, "d": 40}
        assert await Item.order_by("price", "asc").value("name") == "a"
        assert await Item.where("tag", "=", "nope").value("name") is None
    finally:
        await db.dispose()


async def test_first_or_fail() -> None:
    db = await _seed()
    try:
        assert (await Item.where("tag", "=", "z").first_or_fail()).name == "d"
        with pytest.raises(ModelNotFound):
            await Item.where("tag", "=", "nope").first_or_fail()
    finally:
        await db.dispose()
