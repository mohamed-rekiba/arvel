"""C3a — query builder breadth: select/distinct/where-variants/aggregates/paginate."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import Builder, ConnectionResolver

_md = sa.MetaData()
products = sa.Table(
    "products",
    _md,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String),
    sa.Column("category", sa.String),
    sa.Column("price", sa.Integer),
    sa.Column("discontinued_at", sa.String, nullable=True),
)


async def _seed() -> ConnectionResolver:
    db = ConnectionResolver()
    await db.execute(sa.schema.CreateTable(products))
    rows = [
        {"name": "a", "category": "tools", "price": 10, "discontinued_at": None},
        {"name": "b", "category": "tools", "price": 30, "discontinued_at": "2020-01-01"},
        {"name": "c", "category": "food", "price": 20, "discontinued_at": None},
    ]
    for row in rows:
        await Builder(products, db).insert(row)
    return db


def test_select_columns_and_distinct() -> None:
    stmt = Builder(products).select("category").distinct().to_select()
    compiled = str(stmt.compile(dialect=sa.dialects.sqlite.dialect()))
    assert "DISTINCT" in compiled.upper()
    assert "category" in compiled
    assert "price" not in compiled.split("FROM")[0]  # only selected column


async def test_where_in_and_or_where() -> None:
    db = await _seed()
    try:
        rows = await Builder(products, db).where_in("category", ["food", "tools"]).get()
        assert len(rows) == 3
        either = await Builder(products, db).where(name="a").or_where(name="c").get()
        assert {r["name"] for r in either} == {"a", "c"}
    finally:
        await db.dispose()


async def test_where_null() -> None:
    db = await _seed()
    try:
        live = await Builder(products, db).where_null("discontinued_at").get()
        assert {r["name"] for r in live} == {"a", "c"}
        gone = await Builder(products, db).where_not_null("discontinued_at").get()
        assert {r["name"] for r in gone} == {"b"}
    finally:
        await db.dispose()


async def test_aggregates() -> None:
    db = await _seed()
    try:
        assert await Builder(products, db).count() == 3
        assert await Builder(products, db).where(category="tools").count() == 2
        assert await Builder(products, db).sum("price") == 60
        assert await Builder(products, db).avg("price") == 20
        assert await Builder(products, db).min("price") == 10
        assert await Builder(products, db).max("price") == 30
        assert await Builder(products, db).where(name="zzz").exists() is False
        assert await Builder(products, db).where(name="a").exists() is True
    finally:
        await db.dispose()


async def test_order_limit_offset() -> None:
    db = await _seed()
    try:
        rows = await Builder(products, db).order_by("price", "desc").limit(1).get()
        assert rows[0]["name"] == "b"
        page2 = await Builder(products, db).order_by("price").limit(1).offset(1).get()
        assert page2[0]["name"] == "c"
    finally:
        await db.dispose()


async def test_paginate() -> None:
    db = await _seed()
    try:
        result = await Builder(products, db).order_by("price").paginate(per_page=2, page=1)
        assert result["total"] == 3
        assert result["last_page"] == 2
        assert len(result["data"]) == 2
    finally:
        await db.dispose()
