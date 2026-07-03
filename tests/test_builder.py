"""T5.2 — query builder on SQLAlchemy Core: constructs + execution."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

from arvel.database import Builder, ConnectionResolver

_md = sa.MetaData()
users = sa.Table(
    "users",
    _md,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String),
    sa.Column("active", sa.Boolean),
)


def test_to_select_is_core_construct() -> None:
    stmt = Builder(users).where(active=True).to_select()
    assert isinstance(stmt, sa.Select)


def test_where_operators() -> None:
    stmt = Builder(users).where("id", ">", 5).where("name", "like", "a%").to_select()
    compiled = str(stmt.compile(dialect=sqlite.dialect()))
    assert "id >" in compiled
    assert "LIKE" in compiled.upper()


def test_where_ilike_is_case_insensitive_on_every_dialect() -> None:
    """`where("col", "ilike", pat)` — ILIKE on PostgreSQL; SQLAlchemy lowers both sides on
    dialects without native ILIKE (SQLite/MySQL), so the semantics hold everywhere."""
    builder = Builder(users).where("name", "ilike", "%CARA%")
    pg = str(builder.to_select().compile(dialect=postgresql.dialect()))
    lite = str(builder.to_select().compile(dialect=sqlite.dialect()))
    assert "ILIKE" in pg.upper()
    assert "lower(" in lite.lower()


def test_same_builder_compiles_multi_dialect() -> None:
    builder = Builder(users).where(active=True)
    pg = str(builder.to_select().compile(dialect=postgresql.dialect()))
    lite = str(builder.to_select().compile(dialect=sqlite.dialect()))
    assert "users" in pg and "users" in lite
    assert pg != lite  # bind-param style differs per dialect


def test_insert_update_delete_constructs() -> None:
    assert isinstance(Builder(users).to_insert({"name": "a"}), sa.Insert)
    assert isinstance(Builder(users).where(id=1).to_update({"name": "b"}), sa.Update)
    assert isinstance(Builder(users).where(id=1).to_delete(), sa.Delete)


async def test_execution_roundtrip() -> None:
    db = ConnectionResolver()
    try:
        await db.execute(sa.schema.CreateTable(users))
        await Builder(users, db).insert({"name": "ada", "active": True})
        await Builder(users, db).insert({"name": "bob", "active": False})

        rows = await Builder(users, db).where(active=True).get()
        assert [r["name"] for r in rows] == ["ada"]

        first = await Builder(users, db).where("name", "=", "bob").first()
        assert first is not None
        assert first["active"] is False or first["active"] == 0

        await Builder(users, db).where(name="bob").update({"active": True})
        active = await Builder(users, db).where(active=True).get()
        assert {r["name"] for r in active} == {"ada", "bob"}

        await Builder(users, db).where(name="ada").delete()
        remaining = await Builder(users, db).get()
        assert [r["name"] for r in remaining] == ["bob"]
    finally:
        await db.dispose()
