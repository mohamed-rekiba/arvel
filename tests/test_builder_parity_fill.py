"""Query-builder parity fill (2.5): union/union_all, nested-closure where-groups, where_not/
where_any/where_all, insert_get_id/insert_or_ignore, Builder-level increment/decrement,
in_random_order/reorder, truncate — plus edge-case fixes (upsert([]) no-op, where_in()'s `_bind`
adaptation, chunk_by_id() leaving the builder reusable). Grouped-where precedence is proven by
query RESULTS on fixture data, never by inspecting compiled SQL strings.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa

from arvel import Model
from arvel.database import ConnectionResolver, UnsupportedDriverOperation
from arvel.database.builder import Builder
from arvel.dates import Date


class Doc(Model):
    __table_name__ = "parity_fill_docs"
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "price": int, "tag": str}
    __fillable__: ClassVar[list[str]] = ["name", "price", "tag"]


async def _seed() -> ConnectionResolver:
    db = ConnectionResolver()
    Doc.set_connection(db)
    await db.execute(sa.schema.CreateTable(Doc.__table__))
    for name, price, tag in [("a", 10, "x"), ("b", 20, "y"), ("c", 30, "x"), ("d", 40, "z")]:
        await Doc.create(name=name, price=price, tag=tag)
    return db


# --- union / union_all -------------------------------------------------------
async def test_union_dedupes_and_orders_the_combined_set() -> None:
    db = await _seed()
    try:
        rows = (
            await Doc.where("tag", "=", "x")
            .union(Doc.where("tag", "=", "y"))
            .order_by("price", "desc")
            .get()
        )
        assert [r.name for r in rows] == ["c", "b", "a"]
    finally:
        await db.dispose()


async def test_union_all_keeps_duplicate_rows() -> None:
    db = await _seed()
    try:
        rows = await Doc.where("tag", "=", "x").union_all(Doc.where("tag", "=", "x")).get()
        assert sorted(r.name for r in rows) == ["a", "a", "c", "c"]
    finally:
        await db.dispose()


# --- nested-closure where groups / where_not / where_any / where_all ---------
async def test_closure_where_group_gets_correct_precedence() -> None:
    """(tag=x OR tag=y) AND price>15 — without the group, `x OR y AND price>15` would wrongly
    also match `a` (tag=x, price=10)."""
    db = await _seed()
    try:
        rows = await (
            Doc.where(lambda q: q.where("tag", "=", "x").or_where("tag", "=", "y"))
            .where("price", ">", 15)
            .get()
        )
        assert sorted(r.name for r in rows) == ["b", "c"]
    finally:
        await db.dispose()


async def test_or_where_closure_group() -> None:
    db = await _seed()
    try:
        rows = (
            await Doc.where("tag", "=", "z")
            .or_where(lambda q: q.where("tag", "=", "x").where("price", "=", 30))
            .get()
        )
        assert sorted(r.name for r in rows) == ["c", "d"]
    finally:
        await db.dispose()


async def test_where_not_negates_a_column_condition() -> None:
    db = await _seed()
    try:
        rows = await Doc.where_not("tag", "x").get()
        assert sorted(r.name for r in rows) == ["b", "d"]
        lte = await Doc.where_not("price", ">", 15).get()
        assert [r.name for r in lte] == ["a"]
    finally:
        await db.dispose()


async def test_where_not_negates_a_closure_group() -> None:
    db = await _seed()
    try:
        rows = await Doc.where_not(
            lambda q: q.where("tag", "=", "x").or_where("tag", "=", "y")
        ).get()
        assert [r.name for r in rows] == ["d"]
    finally:
        await db.dispose()


class Pair(Model):
    __table_name__ = "parity_fill_pairs"
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "a": int, "b": int}
    __fillable__: ClassVar[list[str]] = ["name", "a", "b"]


async def _seed_pairs() -> ConnectionResolver:
    db = ConnectionResolver()
    Pair.set_connection(db)
    await db.execute(sa.schema.CreateTable(Pair.__table__))
    for name, a, b in [("p1", 1, 9), ("p2", 9, 1), ("p3", 5, 5), ("p4", 9, 9)]:
        await Pair.create(name=name, a=a, b=b)
    return db


async def test_where_any_ors_across_columns() -> None:
    """Either column matching 9 is enough — proves OR, not just one column being checked."""
    db = await _seed_pairs()
    try:
        rows = await Pair.where_any(["a", "b"], "=", 9).get()
        assert sorted(r.name for r in rows) == ["p1", "p2", "p4"]
    finally:
        await db.dispose()


async def test_where_all_ands_across_columns() -> None:
    """Only the row where BOTH columns match 9 — proves AND, distinguishing it from where_any."""
    db = await _seed_pairs()
    try:
        rows = await Pair.where_all(["a", "b"], "=", 9).get()
        assert [r.name for r in rows] == ["p4"]
    finally:
        await db.dispose()


# --- insert_get_id / insert_or_ignore ----------------------------------------
async def test_insert_get_id_returns_the_new_primary_key() -> None:
    db = await _seed()
    try:
        new_id = await Doc.query().insert_get_id({"name": "e", "price": 5, "tag": "q"})
        assert isinstance(new_id, int)
        found = await Doc.where(Doc.__primary_key__, "=", new_id).first()
        assert found is not None and found.name == "e"
    finally:
        await db.dispose()


_sku_md = sa.MetaData()
skus = sa.Table(
    "parity_fill_skus",
    _sku_md,
    sa.Column("sku", sa.String, primary_key=True),
    sa.Column("price", sa.Integer),
)


async def test_insert_or_ignore_skips_duplicate_rows_on_sqlite() -> None:
    db = ConnectionResolver()
    await db.execute(sa.schema.CreateTable(skus))
    try:
        builder = Builder(skus, db)
        await builder.insert_or_ignore([{"sku": "A", "price": 1}])
        await builder.insert_or_ignore([{"sku": "A", "price": 999}, {"sku": "B", "price": 2}])
        rows = await builder.get()
        assert sorted((r["sku"], r["price"]) for r in rows) == [("A", 1), ("B", 2)]
    finally:
        await db.dispose()


async def test_insert_or_ignore_raises_on_unsupported_dialect() -> None:
    class _FakeDialect:
        name = "oracle"

    class _FakeEngine:
        dialect = _FakeDialect()

    db = ConnectionResolver()
    db.engine = lambda *args, **kwargs: _FakeEngine()  # type: ignore[method-assign]
    with pytest.raises(UnsupportedDriverOperation):
        await Builder(skus, db).insert_or_ignore([{"sku": "A", "price": 1}])


async def test_upsert_empty_rows_is_a_noop() -> None:
    db = ConnectionResolver()
    await db.execute(sa.schema.CreateTable(skus))
    try:
        result = await Builder(skus, db).upsert([], ["sku"])
        assert result.rowcount == 0
    finally:
        await db.dispose()


# --- Builder-level increment/decrement ---------------------------------------
async def test_builder_increment_with_extra_columns() -> None:
    db = await _seed()
    try:
        await Doc.where("tag", "=", "x").increment("price", 5, extra={"tag": "xx"})
        rows = sorted(await Doc.get(), key=lambda r: r.name)
        assert [(r.name, r.price, r.tag) for r in rows] == [
            ("a", 15, "xx"),
            ("b", 20, "y"),
            ("c", 35, "xx"),
            ("d", 40, "z"),
        ]
    finally:
        await db.dispose()


async def test_builder_decrement() -> None:
    db = await _seed()
    try:
        await Doc.where("name", "=", "a").decrement("price", 3)
        found = await Doc.where("name", "=", "a").first()
        assert found.price == 7
    finally:
        await db.dispose()


# --- in_random_order / reorder / truncate ------------------------------------
async def test_in_random_order_returns_the_same_row_set() -> None:
    db = await _seed()
    try:
        rows = await Doc.query().in_random_order().get()
        assert sorted(r.name for r in rows) == ["a", "b", "c", "d"]
    finally:
        await db.dispose()


async def test_reorder_drops_and_replaces_ordering() -> None:
    db = await _seed()
    try:
        rows = await Doc.order_by("price", "desc").reorder("price", "asc").get()
        assert [r.name for r in rows] == ["a", "b", "c", "d"]
        cleared = Doc.order_by("price", "desc").reorder()
        assert cleared._order == [] and cleared._order_specs == []
    finally:
        await db.dispose()


async def test_truncate_empties_the_table_on_sqlite() -> None:
    db = await _seed()
    try:
        await Doc.query().truncate()
        assert await Doc.count() == 0
    finally:
        await db.dispose()


# --- where_in() Date-value adaptation -----------------------------------------
class Event(Model):
    __table_name__ = "parity_fill_events"
    __timestamps__ = False
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "posted_at": _dt.datetime}
    __fillable__: ClassVar[list[str]] = ["name", "posted_at"]


def _at(iso: str) -> _dt.datetime:
    return Date.parse(iso).raw.to_tz("UTC").to_stdlib()


async def test_where_in_adapts_date_values_like_the_3_arg_where() -> None:
    db = ConnectionResolver()
    Event.set_connection(db)
    await db.execute(sa.schema.CreateTable(Event.__table__))
    try:
        await Event.create(name="first", posted_at=_at("2024-01-01 10:00:00"))
        await Event.create(name="second", posted_at=_at("2024-02-01 10:00:00"))
        rows = await Event.where_in("posted_at", [Date.parse("2024-01-01 10:00:00")]).get()
        assert [r.name for r in rows] == ["first"]
    finally:
        await db.dispose()


# --- chunk_by_id() must leave the builder reusable ---------------------------
async def test_chunk_by_id_reused_builder_gives_identical_results_twice() -> None:
    db = await _seed()
    try:
        query = Doc.query()
        first_pass: list[str] = []
        await query.chunk_by_id(2, lambda rows: first_pass.extend(r.name for r in rows))
        second_pass: list[str] = []
        await query.chunk_by_id(2, lambda rows: second_pass.extend(r.name for r in rows))
        assert first_pass == second_pass == ["a", "b", "c", "d"]
    finally:
        await db.dispose()
