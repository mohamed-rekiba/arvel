"""Advanced DB (doc 08) — schema ops (views/MV/extensions/functions). Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database.schema import (
    create_extension,
    create_function,
    create_materialized_view,
    create_view,
    drop_materialized_view,
    drop_view,
    refresh_materialized_view,
)

users = sa.Table(
    "users", sa.MetaData(), sa.Column("id", sa.Integer), sa.Column("active", sa.Boolean)
)


def test_create_view() -> None:
    ddl = str(create_view("active_users", sa.select(users.c.id).where(users.c.active.is_(True))))
    assert ddl.startswith("CREATE VIEW active_users AS")
    assert "SELECT" in ddl.upper()


def test_create_materialized_view_and_refresh() -> None:
    assert "CREATE MATERIALIZED VIEW mv AS" in str(
        create_materialized_view("mv", sa.select(users.c.id))
    )
    assert str(refresh_materialized_view("mv")) == "REFRESH MATERIALIZED VIEW mv"
    assert "CONCURRENTLY" in str(refresh_materialized_view("mv", concurrently=True))


def test_create_extension() -> None:
    assert str(create_extension("vector")) == 'CREATE EXTENSION IF NOT EXISTS "vector"'


def test_create_function() -> None:
    ddl = str(
        create_function(
            "increment", [("a", "int"), ("b", "int")], returns="int", body="BEGIN RETURN a+b; END;"
        )
    )
    assert "CREATE OR REPLACE FUNCTION increment(a int, b int)" in ddl
    assert "RETURNS int" in ddl
    assert "LANGUAGE plpgsql" in ddl


def test_drops() -> None:
    assert str(drop_view("v")) == "DROP VIEW IF EXISTS v"
    assert str(drop_materialized_view("mv")) == "DROP MATERIALIZED VIEW IF EXISTS mv"
