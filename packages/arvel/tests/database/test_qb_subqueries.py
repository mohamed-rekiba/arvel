"""Eloquent-parity (backlog 005, S3): subquery FROM / JOIN / SELECT.

from_sub, join_sub / left_join_sub, select_sub, add_select.
"""

from __future__ import annotations

from arvel.database import Model
from sqlalchemy import Integer, String, func
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class SqUser(Model):
    __tablename__ = "sq_users"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    active: Mapped[bool] = mapped_column(default=True)


class SqOrder(Model):
    __tablename__ = "sq_orders"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def _seed() -> tuple[SqUser, SqUser]:
    alice = await SqUser.create(name="Alice", active=True)
    bob = await SqUser.create(name="Bob", active=False)
    await SqOrder.create(user_id=alice.id, amount=50)
    await SqOrder.create(user_id=alice.id, amount=300)
    await SqOrder.create(user_id=bob.id, amount=25)
    return alice, bob


async def test_from_sub_selects_derived_table(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await _seed()

    rows = await SqUser.from_sub(SqUser.where(SqUser.active.is_(True)), "active_users").get()

    assert {r["name"] for r in rows} == {"Alice"}
    assert all(r["active"] for r in rows)


async def test_join_sub_inner(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    alice, _bob = await _seed()

    high_value = SqOrder.where(SqOrder.amount >= 100)
    rows = await SqUser.join_sub(high_value, "hv", lambda hv: hv.c.user_id == SqUser.id).get()

    assert {u.id for u in rows} == {alice.id}


async def test_left_join_sub_keeps_unmatched(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    alice, bob = await _seed()

    high_value = SqOrder.where(SqOrder.amount >= 100)
    rows = await SqUser.left_join_sub(high_value, "hv", lambda hv: hv.c.user_id == SqUser.id).get()

    # Both users survive the LEFT JOIN even though Bob has no high-value order.
    assert {u.id for u in rows} == {alice.id, bob.id}


async def test_select_sub_appends_correlated_column(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    await _seed()

    top_amount = (
        SqOrder.where(SqOrder.user_id == SqUser.id)
        .order_by_desc("amount")
        .limit(1)
        .select("amount")
    )
    rows = await SqUser.select_sub(top_amount, "top_amount").order_by("name").get()

    by_name = {u.name: u for u in rows}
    assert by_name["Alice"].top_amount == 300
    assert by_name["Bob"].top_amount == 25


async def test_add_select_appends_expression(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await _seed()

    rows = (
        await SqUser.add_select(func.upper(SqUser.name).label("upper_name")).order_by("name").get()
    )

    by_name = {u.name: u for u in rows}
    assert by_name["Alice"].upper_name == "ALICE"
    # The model's own columns are still loaded — add_select appends, not replaces.
    assert by_name["Bob"].active is False
