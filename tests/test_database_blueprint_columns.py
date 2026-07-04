"""Blueprint column-type breadth: every new column type must compile under BOTH the PostgreSQL
and SQLite dialects from the same Blueprint call — no raw SQL, generic SA types only.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from arvel.database.schema import Blueprint


def _compiles_both(table: sa.Table) -> tuple[str, str]:
    pg = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    lite = str(CreateTable(table).compile(dialect=sqlite.dialect()))
    return pg, lite


def _table_with(build) -> sa.Table:  # type: ignore[no-untyped-def]
    bp = Blueprint("things")
    bp.id()
    build(bp)
    return bp.to_table(sa.MetaData())


def test_json_and_jsonb_compile_both_dialects() -> None:
    table = _table_with(lambda t: (t.json("payload"), t.jsonb("doc")))
    assert {"payload", "doc"} <= set(table.c.keys())
    pg, lite = _compiles_both(table)
    assert "JSONB" in pg.upper()  # jsonb maps to JSONB on Postgres
    assert "JSON" in lite.upper()


def test_uuid_compiles_both_dialects() -> None:
    table = _table_with(lambda t: t.uuid("public_id"))
    pg, lite = _compiles_both(table)
    assert "public_id" in pg and "public_id" in lite


def test_decimal_carries_precision_scale() -> None:
    table = _table_with(lambda t: t.decimal("amount", 12, 2))
    assert isinstance(table.c.amount.type, sa.Numeric)
    assert table.c.amount.type.precision == 12
    assert table.c.amount.type.scale == 2
    _compiles_both(table)


def test_float_date_datetime_time_compile() -> None:
    def build(t: Blueprint) -> None:
        t.float("ratio")
        t.date("d")
        t.datetime("dt")
        t.time("tm")

    table = _table_with(build)
    assert {"ratio", "d", "dt", "tm"} <= set(table.c.keys())
    assert isinstance(table.c.ratio.type, sa.Float)
    assert isinstance(table.c.d.type, sa.Date)
    assert isinstance(table.c.tm.type, sa.Time)
    _compiles_both(table)


def test_enum_compiles_both_dialects() -> None:
    table = _table_with(lambda t: t.enum("status", "draft", "published", "archived"))
    pg, lite = _compiles_both(table)  # SQLite degrades Enum to VARCHAR+CHECK — still compiles
    assert "status" in pg and "status" in lite


def test_morphs_creates_id_and_type_columns() -> None:
    table = _table_with(lambda t: t.morphs("commentable"))
    assert "commentable_id" in table.c
    assert "commentable_type" in table.c
    # matches what MorphTo/MorphMany read: <name>_id (int) + <name>_type (string)
    assert isinstance(table.c.commentable_id.type, (sa.BigInteger, sa.Integer))
    assert isinstance(table.c.commentable_type.type, sa.String)
    assert not table.c.commentable_id.nullable
    _compiles_both(table)


def test_nullable_morphs_are_nullable() -> None:
    table = _table_with(lambda t: t.nullable_morphs("imageable"))
    assert table.c.imageable_id.nullable
    assert table.c.imageable_type.nullable


def test_soft_deletes_adds_nullable_deleted_at() -> None:
    table = _table_with(lambda t: t.soft_deletes())
    assert "deleted_at" in table.c
    assert table.c.deleted_at.nullable
    _compiles_both(table)
