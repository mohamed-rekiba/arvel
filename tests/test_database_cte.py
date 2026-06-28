"""Advanced DB (doc 08) — CTE / recursive-CTE builder methods (Core, multi-dialect)."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import Builder

_md = sa.MetaData()
nodes = sa.Table(
    "nodes",
    _md,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("parent_id", sa.Integer),
    sa.Column("name", sa.String),
)


def test_to_cte_is_a_core_cte() -> None:
    cte = Builder(nodes).where(parent_id=None).to_cte("roots")
    assert isinstance(cte, sa.sql.selectable.CTE)
    compiled = str(sa.select(cte).compile()).upper()
    assert "WITH" in compiled
    assert "ROOTS" in compiled


def test_recursive_cte_compiles_with_recursive() -> None:
    stmt = Builder(nodes).recursive_cte(
        "tree",
        anchor=Builder(nodes).where(id=1),
        recursive=lambda cte: sa.select(nodes).join(cte, nodes.c.parent_id == cte.c.id),
    )
    assert isinstance(stmt, sa.Select)
    assert "RECURSIVE" in str(stmt.compile()).upper()


def test_cte_compiles_multi_dialect() -> None:
    from sqlalchemy.dialects import postgresql, sqlite

    stmt = sa.select(Builder(nodes).to_cte("c"))
    assert "nodes" in str(stmt.compile(dialect=postgresql.dialect()))
    assert "nodes" in str(stmt.compile(dialect=sqlite.dialect()))
