"""Full-text search — a `tsvector` Blueprint column (Postgres TSVECTOR / portable Text) plus
`Builder.where_fulltext` emitting `to_tsvector(...) @@ plainto_tsquery(...)`."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from arvel.database import Builder, ConnectionResolver
from arvel.database.schema import Blueprint

_md = sa.MetaData()
articles = sa.Table(
    "articles",
    _md,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("body", sa.Text),
)


def test_tsvector_column_is_tsvector_on_postgres() -> None:
    bp = Blueprint("docs")
    bp.id()
    bp.tsvector("search")
    ddl = str(sa.schema.CreateTable(bp.to_table()).compile(dialect=postgresql.dialect()))
    assert "TSVECTOR" in ddl.upper()


async def test_tsvector_column_is_portable_text_on_sqlite() -> None:
    bp = Blueprint("docs")
    bp.id()
    bp.tsvector("search")
    db = ConnectionResolver()
    try:
        await db.execute(sa.schema.CreateTable(bp.to_table()))  # Text on sqlite — no error
    finally:
        await db.dispose()


def test_where_fulltext_compiles_to_tsquery_match() -> None:
    stmt = Builder(articles).where_fulltext("body", "fast async python").to_select()
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "to_tsvector" in sql
    assert "@@" in sql
    assert "plainto_tsquery" in sql


def test_where_fulltext_honors_language() -> None:
    stmt = Builder(articles).where_fulltext("body", "rapide", language="french").to_select()
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert "french" in compiled.params.values()
