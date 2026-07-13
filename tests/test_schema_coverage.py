"""Coverage — Blueprint column types + schema ops + core_columns (doc 08)."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database.schema import (
    Blueprint,
    create_function,
    drop_materialized_view,
    drop_view,
)


def test_all_column_types() -> None:
    bp = Blueprint("things")
    bp.id()
    bp.big_integer("big")
    bp.integer("count")
    bp.string("name", 50)
    bp.text("body")
    bp.boolean("active")
    bp.foreign_id("owner_id")
    bp.timestamps()
    columns = bp.core_columns()
    assert all(isinstance(c, sa.Column) for c in columns)
    table = bp.to_table(sa.MetaData())
    assert {
        "id",
        "big",
        "count",
        "name",
        "body",
        "active",
        "owner_id",
        "created_at",
        "updated_at",
    } <= set(table.c.keys())
    assert table.c.name.type.length == 50


def test_create_function_and_drops() -> None:
    fn = str(create_function("inc", [("a", "int")], returns="int", body="BEGIN END;"))
    assert "CREATE OR REPLACE FUNCTION inc(a int)" in fn
    assert str(drop_view("v")) == "DROP VIEW IF EXISTS v"
    assert str(drop_materialized_view("mv")) == "DROP MATERIALIZED VIEW IF EXISTS mv"
