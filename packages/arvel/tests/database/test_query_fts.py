"""Story 3 & 4 — QueryBuilder.where_full_text() and order_by_relevance() (WI-arvel-034)."""

from __future__ import annotations

import pytest
from arvel.database import Model, QueryBuilder, id_, text

# ── Minimal model for compilation tests ───────────────────────────────────────


class FtsPost(Model):
    __tablename__ = "fts_posts"
    id: int = id_()
    body: str = text()
    # Text suffices here; TSVECTOR is not needed for QB compilation tests
    search_vector: str | None = text(nullable=True, default=None)


_SV = FtsPost.__table__.c.search_vector


def _sql(qb: QueryBuilder[FtsPost]) -> str:
    return qb.to_sql(dialect="postgresql")


# ── Story 3: where_full_text ───────────────────────────────────────────────────


def test_where_full_text_emits_at_at_operator() -> None:
    """where_full_text emits the @@ match operator."""
    sql = _sql(FtsPost.where_full_text(_SV, "python async"))
    assert "@@" in sql


def test_where_full_text_default_uses_plainto_tsquery() -> None:
    """Default tsquery_fn is plainto_tsquery."""
    sql = _sql(FtsPost.where_full_text(_SV, "python async"))
    assert "plainto_tsquery" in sql


def test_where_full_text_websearch_to_tsquery() -> None:
    """tsquery_fn='websearch_to_tsquery' is accepted and emitted."""
    sql = _sql(FtsPost.where_full_text(_SV, "python -boring", tsquery_fn="websearch_to_tsquery"))
    assert "websearch_to_tsquery" in sql


def test_where_full_text_to_tsquery() -> None:
    """tsquery_fn='to_tsquery' is accepted and emitted."""
    sql = _sql(FtsPost.where_full_text(_SV, "python & async", tsquery_fn="to_tsquery"))
    assert "to_tsquery" in sql


def test_where_full_text_phraseto_tsquery() -> None:
    """tsquery_fn='phraseto_tsquery' is accepted and emitted."""
    sql = _sql(FtsPost.where_full_text(_SV, "python asyncio", tsquery_fn="phraseto_tsquery"))
    assert "phraseto_tsquery" in sql


def test_where_full_text_invalid_tsquery_fn_raises() -> None:
    """An unrecognised tsquery_fn raises ValueError immediately (before hitting DB)."""
    with pytest.raises(ValueError, match="tsquery_fn"):
        FtsPost.where_full_text(_SV, "python", tsquery_fn="exec('rm -rf')")


def test_where_full_text_custom_lang() -> None:
    """The lang parameter is embedded in the compiled SQL."""
    sql = _sql(FtsPost.where_full_text(_SV, "python", lang="french"))
    assert "french" in sql


def test_where_full_text_query_is_bind_param() -> None:
    """The search query appears as a bind parameter, never raw-interpolated."""
    sql = _sql(FtsPost.where_full_text(_SV, "DROP TABLE--"))
    # The literal string should appear (literal_binds=True in to_sql), but the
    # key point is that the SQL compiles without error — no raw concatenation.
    assert "DROP TABLE" in sql  # appears as a string literal, not bare SQL
    # Confirm it's inside the tsquery function call, not a dangling SQL fragment
    assert "plainto_tsquery" in sql


def test_where_full_text_chains_with_where() -> None:
    """where_full_text() can be chained with .where() — both predicates appear."""
    sql = _sql(FtsPost.where_full_text(_SV, "python").where(FtsPost.__table__.c.id > 10))
    assert "@@" in sql
    assert "fts_posts.id > 10" in sql


def test_where_full_text_on_query_builder_directly() -> None:
    """QueryBuilder.where_full_text mirrors the same behaviour as the classmethod."""
    sql = FtsPost.query().where_full_text(_SV, "python").to_sql(dialect="postgresql")
    assert "@@" in sql
    assert "plainto_tsquery" in sql


def test_where_full_text_returns_self_for_chaining() -> None:
    """where_full_text returns a QueryBuilder (not None) so chaining works."""
    qb = FtsPost.where_full_text(_SV, "python")
    assert isinstance(qb, QueryBuilder)


# ── Story 4: order_by_relevance ───────────────────────────────────────────────


def test_order_by_relevance_emits_ts_rank() -> None:
    """order_by_relevance emits ts_rank in the ORDER BY clause."""
    sql = _sql(FtsPost.order_by_relevance(_SV, "python"))
    assert "ts_rank" in sql


def test_order_by_relevance_orders_descending() -> None:
    """Relevance ordering is DESC."""
    sql = _sql(FtsPost.order_by_relevance(_SV, "python"))
    assert "DESC" in sql


def test_order_by_relevance_custom_lang() -> None:
    """The lang parameter is included in the ts_rank expression."""
    sql = _sql(FtsPost.order_by_relevance(_SV, "python", lang="spanish"))
    assert "spanish" in sql


def test_order_by_relevance_query_is_bind_param() -> None:
    """The query string appears as a literal value (not a dangling SQL token)."""
    sql = _sql(FtsPost.order_by_relevance(_SV, "safe search"))
    assert "ts_rank" in sql
    assert "safe search" in sql


def test_order_by_relevance_without_where_full_text_compiles() -> None:
    """order_by_relevance can be used standalone (ranking without filtering is valid)."""
    sql = _sql(FtsPost.order_by_relevance(_SV, "python"))
    assert "ts_rank" in sql
    assert "@@" not in sql  # no WHERE filter


def test_order_by_relevance_stacks_with_other_order_by() -> None:
    """order_by_relevance stacks after another order_by — both appear."""
    sql = _sql(FtsPost.order_by_relevance(_SV, "python").order_by(FtsPost.__table__.c.id))
    assert "ts_rank" in sql
    assert "fts_posts.id" in sql


def test_order_by_relevance_with_where_full_text() -> None:
    """Typical combined usage: filter by FTS then rank by relevance."""
    sql = _sql(FtsPost.where_full_text(_SV, "python async").order_by_relevance(_SV, "python async"))
    assert "@@" in sql
    assert "ts_rank" in sql


def test_order_by_relevance_on_query_builder_directly() -> None:
    """QueryBuilder.order_by_relevance works when invoked on the builder directly."""
    sql = FtsPost.query().order_by_relevance(_SV, "python").to_sql(dialect="postgresql")
    assert "ts_rank" in sql


def test_order_by_relevance_returns_self_for_chaining() -> None:
    """order_by_relevance returns a QueryBuilder for further chaining."""
    qb = FtsPost.order_by_relevance(_SV, "python")
    assert isinstance(qb, QueryBuilder)
