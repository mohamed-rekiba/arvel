"""Eloquent-parity (backlog 005, Sprint A): nested WHERE groups, unless/tap, efficient exists."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model
from arvel.database.query import QueryBuilder
from sqlalchemy import Integer, String, event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class Gadget(Model):
    __tablename__ = "gadgets_qcx"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tag: Mapped[str] = mapped_column(String(40), nullable=False, default="")


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def _seed(engine: Any) -> None:
    await _create_tables(engine)
    await Gadget.create(name="alpha", qty=1, tag="x")
    await Gadget.create(name="beta", qty=2, tag="y")
    await Gadget.create(name="gamma", qty=9, tag="x")


# ── S2: nested WHERE groups ────────────────────────────────────────────────


async def test_where_callback_groups_or_within_and(engine: Any, session: AsyncSession) -> None:
    await _seed(engine)

    def _qty_group(q: QueryBuilder[Gadget]) -> QueryBuilder[Gadget]:
        return q.or_where(Gadget.qty == 1, Gadget.qty == 9)

    # (qty == 1 OR qty == 9) AND tag == "x"  → alpha, gamma
    rows = await Gadget.where(_qty_group).where(Gadget.tag == "x").order_by("name").all()
    assert [r.name for r in rows] == ["alpha", "gamma"]


async def test_or_where_callback_groups_and_within_or(engine: Any, session: AsyncSession) -> None:
    await _seed(engine)

    def _and_group(q: QueryBuilder[Gadget]) -> QueryBuilder[Gadget]:
        return q.where(Gadget.qty == 9).where(Gadget.tag == "x")

    # or_where ORs its own terms; a group callback is one such term:
    # tag == "y" OR (qty == 9 AND tag == "x")  → beta, gamma
    rows = await Gadget.query().or_where(Gadget.tag == "y", _and_group).order_by("name").all()
    assert [r.name for r in rows] == ["beta", "gamma"]


async def test_where_group_callback_returning_none_raises(
    engine: Any, session: AsyncSession
) -> None:
    await _create_tables(engine)

    def _bad(q: QueryBuilder[Gadget]) -> Any:
        q.where(Gadget.qty == 1)  # mutates nothing (builder is immutable), returns None

    with pytest.raises(TypeError):
        Gadget.where(_bad)


# ── S4: unless / tap ───────────────────────────────────────────────────────


async def test_unless_runs_callback_when_condition_falsy(
    engine: Any, session: AsyncSession
) -> None:
    await _seed(engine)
    rows = await (
        Gadget.query().unless(False, lambda q: q.where(Gadget.tag == "x")).order_by("name").all()
    )
    assert [r.name for r in rows] == ["alpha", "gamma"]


async def test_unless_runs_otherwise_when_condition_truthy(
    engine: Any, session: AsyncSession
) -> None:
    await _seed(engine)
    rows = await (
        Gadget.query()
        .unless(
            True,
            lambda q: q.where(Gadget.tag == "x"),
            lambda q: q.where(Gadget.tag == "y"),
        )
        .all()
    )
    assert [r.name for r in rows] == ["beta"]


async def test_tap_invokes_callback_and_returns_passthrough(
    engine: Any, session: AsyncSession
) -> None:
    await _seed(engine)
    seen: list[QueryBuilder[Gadget]] = []
    qb = Gadget.where(Gadget.tag == "x")
    tapped = qb.tap(lambda q: seen.append(q))
    assert len(seen) == 1
    # tap is side-effect only: the returned builder still has the original filter
    rows = await tapped.order_by("name").all()
    assert [r.name for r in rows] == ["alpha", "gamma"]


async def test_tap_ignores_callback_return_value(engine: Any, session: AsyncSession) -> None:
    await _seed(engine)
    # Callback narrows a *copy* and returns it; tap must ignore that and keep the
    # pre-tap query unchanged.
    qb = Gadget.query()
    tapped = qb.tap(lambda q: q.where(Gadget.qty == 999))
    assert await tapped.count() == 3


# ── S7: efficient exists / doesnt_exist ────────────────────────────────────


async def test_exists_true_and_false(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    assert await Gadget.where(name="nope").exists() is False
    await Gadget.create(name="solo", qty=1, tag="z")
    assert await Gadget.where(name="solo").exists() is True


async def test_doesnt_exist(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    assert await Gadget.where(name="ghost").doesnt_exist() is True
    await Gadget.create(name="ghost", qty=1, tag="z")
    assert await Gadget.where(name="ghost").doesnt_exist() is False


async def test_exists_emits_sql_exists_not_count(engine: Any, session: AsyncSession) -> None:
    await _seed(engine)
    captured: list[str] = []

    def _capture(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        captured.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _capture)
    try:
        await Gadget.where(Gadget.tag == "x").exists()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _capture)

    joined = " ".join(captured).lower()
    assert "exists" in joined
    assert "count(" not in joined
