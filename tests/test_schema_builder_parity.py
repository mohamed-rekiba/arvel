"""Schema builder — Laravel Blueprint column-type parity. The laravel/laravel skeleton's migrations use
``timestamp`` / ``longText`` / ``mediumText`` / ``char`` / ``unsignedInteger`` (+ small/big/tiny). These
must exist (snake_case) so a Laravel migration ports verbatim and runs."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from arvel.database.schema import Blueprint


def test_laravel_column_types_exist_and_map() -> None:
    bp = Blueprint("things")
    bp.id()
    bp.timestamp("published_at")
    bp.long_text("body")
    bp.medium_text("summary")
    bp.char("code", 8)
    bp.unsigned_integer("views")
    bp.unsigned_big_integer("big")
    bp.unsigned_small_integer("small")
    bp.unsigned_tiny_integer("tiny")
    cols = bp.to_table(sa.MetaData()).c

    assert isinstance(cols.published_at.type, sa.DateTime)
    assert isinstance(cols.body.type, sa.Text)
    assert isinstance(cols.summary.type, sa.Text)
    assert isinstance(cols.code.type, sa.CHAR) and cols.code.type.length == 8
    # base (portable) types — integer family
    assert isinstance(cols.views.type, sa.Integer) and not isinstance(
        cols.views.type, sa.BigInteger
    )
    assert isinstance(cols.big.type, sa.BigInteger)
    assert isinstance(cols.small.type, sa.SmallInteger)
    assert isinstance(cols.tiny.type, sa.SmallInteger)


def test_unsigned_is_truly_unsigned_on_mysql() -> None:
    # cross-dialect: portable Integer elsewhere, real UNSIGNED on MySQL (Laravel parity)
    bp = Blueprint("t")
    bp.unsigned_integer("n")
    col_type = bp.to_table(sa.MetaData()).c.n.type
    assert col_type.dialect_impl(mysql.dialect()).unsigned is True


def test_cross_dialect_ddl_rendering() -> None:
    # the point of the change: MySQL gets its specific types; Postgres/SQLite get portable ones
    from sqlalchemy.dialects import sqlite

    bp = Blueprint("t4")
    bp.long_text("body")
    bp.medium_text("summary")
    bp.unsigned_big_integer("author_id")
    cols = bp.to_table(sa.MetaData()).c
    my = mysql.dialect()
    assert "LONGTEXT" in cols.body.type.compile(my)
    assert "MEDIUMTEXT" in cols.summary.type.compile(my)
    assert "UNSIGNED" in cols.author_id.type.compile(my)
    # portable elsewhere — no MySQL-isms
    assert cols.body.type.compile(sqlite.dialect()) == "TEXT"
    assert "UNSIGNED" not in cols.author_id.type.compile(sqlite.dialect())


def test_timestamp_is_nullable_chainable() -> None:
    bp = Blueprint("t2")
    bp.id()
    bp.timestamp("verified_at").nullable()
    assert bp.to_table(sa.MetaData()).c.verified_at.nullable is True


def test_primary_marks_a_non_integer_primary_key() -> None:
    # t.uuid("id").primary() must produce a non-autoincrement PK (CHAR/uuid can't autoincrement),
    # while the integer t.id() PK still autoincrements.
    bp = Blueprint("notifications")
    bp.uuid("id").primary()
    bp.string("type")
    table = bp.to_table(sa.MetaData())
    assert [c.name for c in table.primary_key.columns] == ["id"]
    assert table.c.id.autoincrement is False

    ints = Blueprint("widgets")
    ints.id()
    int_table = ints.to_table(sa.MetaData())
    assert int_table.c.id.autoincrement is True
