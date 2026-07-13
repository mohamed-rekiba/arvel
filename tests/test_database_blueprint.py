"""The Blueprint schema DSL over SQLAlchemy Core."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from arvel.database.schema import Blueprint


def _posts() -> sa.Table:
    # A shared metadata holds the FK target (users) so the schema resolves + compiles.
    meta = sa.MetaData()
    users = Blueprint("users")
    users.id()
    users.string("email")
    users.to_table(meta)

    bp = Blueprint("posts")
    bp.id()
    bp.string("title")
    bp.text("body")
    bp.boolean("published").default(value=False)
    bp.foreign_id("user_id").constrained()
    bp.timestamps()
    return bp.to_table(meta)


def test_blueprint_builds_core_table_with_columns() -> None:
    table = _posts()
    assert isinstance(table, sa.Table)
    assert {"id", "title", "body", "published", "user_id", "created_at", "updated_at"} <= set(
        table.c.keys()
    )


def test_id_is_primary_key() -> None:
    assert _posts().c.id.primary_key


def test_constrained_adds_foreign_key_to_inferred_table() -> None:
    table = _posts()
    fks = list(table.c.user_id.foreign_keys)
    assert fks, "user_id should carry a foreign key"
    assert fks[0].target_fullname == "users.id"  # user_id -> users.id (pluralized)


def test_string_length_and_nullable_chain() -> None:
    bp = Blueprint("t")
    bp.string("name", 100).nullable()
    table = bp.to_table(sa.MetaData())
    assert table.c.name.nullable
    assert table.c.name.type.length == 100


def test_blueprint_compiles_multi_dialect() -> None:
    table = _posts()
    assert "posts" in str(CreateTable(table).compile(dialect=sqlite.dialect()))
    assert "posts" in str(CreateTable(table).compile(dialect=postgresql.dialect()))


def test_vector_column_present() -> None:
    bp = Blueprint("embeddings")
    bp.id()
    bp.vector("embedding", 8)
    table = bp.to_table(sa.MetaData())
    assert "embedding" in table.c
