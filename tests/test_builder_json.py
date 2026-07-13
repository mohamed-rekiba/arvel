"""Querying inside JSON columns — where_json (nested path, cross-dialect) + where_json_contains
(Postgres @> containment). Addresses the 'query/search JSON columns' gap."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from arvel.database import Builder, ConnectionResolver

_md = sa.MetaData()
docs = sa.Table(
    "docs",
    _md,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String),
    sa.Column("data", sa.JSON),
)


async def _seed() -> ConnectionResolver:
    db = ConnectionResolver()
    await db.execute(sa.schema.CreateTable(docs))
    rows = [
        {"name": "a", "data": {"lang": "en", "tags": ["x", "y"], "meta": {"v": "1"}}},
        {"name": "b", "data": {"lang": "fr", "tags": ["y", "z"], "meta": {"v": "2"}}},
    ]
    for row in rows:
        await Builder(docs, db).insert(row)
    return db


async def test_where_json_top_level_key() -> None:
    db = await _seed()
    try:
        rows = await Builder(docs, db).where_json("data", "lang", "en").get()
        assert {r["name"] for r in rows} == {"a"}
    finally:
        await db.dispose()


async def test_where_json_nested_path() -> None:
    db = await _seed()
    try:
        rows = await Builder(docs, db).where_json("data", "meta->v", "2").get()
        assert {r["name"] for r in rows} == {"b"}
    finally:
        await db.dispose()


async def test_where_json_dotted_path_equivalent() -> None:
    db = await _seed()
    try:
        rows = await Builder(docs, db).where_json("data", "meta.v", "1").get()
        assert {r["name"] for r in rows} == {"a"}
    finally:
        await db.dispose()


def test_where_json_contains_compiles_to_postgres_containment() -> None:
    stmt = Builder(docs).where_json_contains("data", ["x"]).to_select()
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "@>" in sql


async def test_where_json_like_searches_a_locale_value() -> None:
    db = await _seed()
    try:
        await Builder(docs, db).insert(
            {"name": "c", "data": {"lang": "en", "name_i18n": "Aurora Phone"}}
        )
        rows = await Builder(docs, db).where_json_like("data", "name_i18n", "%Phone%").get()
        assert {r["name"] for r in rows} == {"c"}
    finally:
        await db.dispose()


async def test_where_in_accepts_a_subquery() -> None:
    """where_in with a Select filters DB-side (WHERE id IN (SELECT ...)) — no app-side id list."""
    db = await _seed()
    try:
        await Builder(docs, db).insert({"name": "c", "data": {"lang": "en"}})
        sub = sa.select(docs.c.id).where(docs.c.name.in_(["a", "b"]))  # the "allowed" set
        rows = await Builder(docs, db).where_in("id", sub).get()
        assert {r["name"] for r in rows} == {"a", "b"}  # c excluded by the subquery
    finally:
        await db.dispose()


async def test_where_raw_predicate() -> None:
    db = await _seed()
    try:
        rows = await Builder(docs, db).where_raw("name = 'a'").get()
        assert {r["name"] for r in rows} == {"a"}
    finally:
        await db.dispose()


async def test_where_exists_correlated() -> None:
    db = await _seed()
    try:
        await Builder(docs, db).insert({"name": "c", "data": {"lang": "en"}})
        inner = docs.alias("inner")  # correlate the inner alias to the outer docs row
        sub = sa.select(inner.c.id).where((inner.c.id == docs.c.id) & inner.c.name.in_(["a", "b"]))
        rows = await Builder(docs, db).where_exists(sub).get()
        assert {r["name"] for r in rows} == {"a", "b"}  # only rows whose name is in {a,b}
    finally:
        await db.dispose()
