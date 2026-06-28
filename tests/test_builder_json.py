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
