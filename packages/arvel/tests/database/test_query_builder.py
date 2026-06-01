"""QueryBuilder fluent API."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, QueryBuilder, id_, integer, string
from sqlalchemy.ext.asyncio import AsyncSession


class WidgetB(Model):
    __tablename__ = "widgets_b"
    id: int = id_()
    name: str = string(80)
    qty: int = integer(default=0)


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_where_kwarg_uses_getattr(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    await WidgetB.create(name="alpha", qty=3)
    await WidgetB.create(name="beta", qty=7)
    rows = await WidgetB.where(name="alpha").all()
    assert len(rows) == 1
    assert rows[0].name == "alpha"


async def test_where_kwarg_unknown_column_raises_attribute_error(
    engine: Any, session: AsyncSession
) -> None:
    await _create_tables(engine)
    with pytest.raises(AttributeError):
        WidgetB.where(this_column_does_not_exist="x")


async def test_where_in_filters(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    for i, name in enumerate(["a", "b", "c", "d"]):
        await WidgetB.create(name=name, qty=i)
    rows = await WidgetB.where_in("name", ["a", "c"]).order_by("name").all()
    assert [r.name for r in rows] == ["a", "c"]


async def test_order_limit_offset(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    for i in range(10):
        await WidgetB.create(name=f"w{i}", qty=i)
    rows = await WidgetB.order_by("qty").limit(3).offset(2).all()
    assert [r.qty for r in rows] == [2, 3, 4]


async def test_count_exists(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    assert await WidgetB.count() == 0
    assert await WidgetB.exists() is False
    await WidgetB.create(name="solo", qty=1)
    assert await WidgetB.count() == 1
    assert await WidgetB.exists() is True


async def test_paginate_returns_paginator(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    for i in range(25):
        await WidgetB.create(name=f"w{i}", qty=i)
    page = await WidgetB.order_by("qty").paginate(per_page=10, page=2)
    assert page.total == 25
    assert page.per_page == 10
    assert page.current_page == 2
    assert page.last_page == 3
    assert page.has_more_pages is True
    assert len(page.items) == 10
    assert page.items[0].qty == 10


async def test_pluck_returns_list_of_values(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    for name in ["a", "b", "c"]:
        await WidgetB.create(name=name, qty=0)
    names = await WidgetB.order_by("name").pluck("name")
    assert names == ["a", "b", "c"]


async def test_first_or_fail_raises(engine: Any, session: AsyncSession) -> None:
    from arvel.database import ModelNotFoundError

    await _create_tables(engine)
    with pytest.raises(ModelNotFoundError):
        await WidgetB.where(name="missing").first_or_fail()


async def test_chunk_processes_batches(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    for i in range(7):
        await WidgetB.create(name=f"w{i}", qty=i)
    seen: list[int] = []

    async def collect(batch: list[WidgetB]) -> None:
        seen.extend(w.qty for w in batch)

    await WidgetB.order_by("qty").chunk(3, collect)
    assert seen == list(range(7))


async def test_query_builder_is_generic_in_type() -> None:
    qb: QueryBuilder[WidgetB] = WidgetB.query()
    assert qb._model is WidgetB  # pyright: ignore[reportPrivateUsage]  # test asserts the private generic-binding invariant


# ─── to_sql  ───────────────────────────────────────────


async def test_to_sql_returns_string(engine: Any, session: AsyncSession) -> None:
    """to_sql returns a non-empty string without executing the query."""
    await _create_tables(engine)
    sql = WidgetB.to_sql()
    assert isinstance(sql, str)
    assert len(sql) > 0


async def test_to_sql_includes_where_clause(engine: Any, session: AsyncSession) -> None:
    """to_sql output includes WHERE conditions."""
    await _create_tables(engine)
    sql = WidgetB.where(name="alpha").to_sql()
    assert "alpha" in sql


async def test_to_sql_includes_order_by(engine: Any, session: AsyncSession) -> None:
    """to_sql includes ORDER BY clause."""
    await _create_tables(engine)
    sql = WidgetB.order_by(WidgetB.__table__.c.qty.desc()).to_sql()
    lower = sql.lower()
    assert "order" in lower and "by" in lower and "qty" in lower


async def test_to_sql_includes_limit(engine: Any, session: AsyncSession) -> None:
    """to_sql includes LIMIT clause."""
    await _create_tables(engine)
    sql = WidgetB.limit(5).to_sql()
    assert "5" in sql


async def test_to_sql_does_not_execute_query(engine: Any, session: AsyncSession) -> None:
    """to_sql does not execute any DB statement."""
    await _create_tables(engine)
    query_count = 0

    from sqlalchemy import event as sa_event

    def _count_queries(
        conn: Any,
        cursor: Any,
        statement: Any,
        parameters: Any,
        context: Any,
        executemany: Any,
    ) -> None:
        nonlocal query_count
        if "widgets_b" in statement.lower():
            query_count += 1

    sa_event.listen(engine.sync_engine, "after_cursor_execute", _count_queries)
    try:
        _sql = WidgetB.where(name="alpha").order_by("name").to_sql()
        assert query_count == 0
    finally:
        sa_event.remove(engine.sync_engine, "after_cursor_execute", _count_queries)


async def test_to_sql_with_explicit_dialect(engine: Any, session: AsyncSession) -> None:
    """to_sql(dialect='sqlite') renders SQLite-flavoured SQL."""
    await _create_tables(engine)
    sql = WidgetB.where(name="alpha").to_sql(dialect="sqlite")
    assert isinstance(sql, str)
    assert len(sql) > 0
