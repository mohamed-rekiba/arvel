"""AuditLog query API — filters, ordering, pagination, invalid action guard."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from arvel.context.facade import Context
from arvel.database.model import Model
from arvel_audit import AuditLog, InvalidAuditAction
from arvel_audit.auditable import Auditable
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

pytestmark = pytest.mark.asyncio


class Order(Model, Auditable):
    __tablename__ = "audit_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")


async def test_for_model_returns_chronological_history(tables: None, session: AsyncSession) -> None:
    order = Order(status="new")
    await order.save()
    order.status = "paid"
    await order.save()
    order.status = "shipped"
    await order.save()

    entries = await AuditLog(session).for_model(order).get()
    assert [e.action for e in entries] == ["created", "updated", "updated"]


async def test_by_actor_filters(tables: None, session: AsyncSession) -> None:
    Context.add("user_id", "alice")
    a = Order(status="new")
    await a.save()
    Context.flush()
    Context.add("user_id", "bob")
    b = Order(status="new")
    await b.save()

    alice_entries = await AuditLog(session).by_actor("alice").get()
    assert all(e.actor_id == "alice" for e in alice_entries)
    assert {e.model_id for e in alice_entries} == {str(a.id)}


async def test_action_filter_and_invalid_action(tables: None, session: AsyncSession) -> None:
    order = Order(status="new")
    await order.save()
    order.status = "paid"
    await order.save()

    updated = await AuditLog(session).for_model(order).action("updated").get()
    assert [e.action for e in updated] == ["updated"]

    with pytest.raises(InvalidAuditAction):
        AuditLog(session).action("exploded")


async def test_since_until_window(tables: None, session: AsyncSession) -> None:
    order = Order(status="new")
    await order.save()

    future = datetime.now(UTC) + timedelta(hours=1)
    past = datetime.now(UTC) - timedelta(hours=1)
    assert await AuditLog(session).since(future).count() == 0
    assert await AuditLog(session).since(past).until(future).count() >= 1


async def test_paginate_uses_orm_paginator(tables: None, session: AsyncSession) -> None:
    order = Order(status="new")
    await order.save()
    for status in ("a", "b", "c", "d"):
        order.status = status
        await order.save()

    page = await AuditLog(session).for_model(order).paginate(per_page=2, page=1)
    assert page.per_page == 2
    assert page.current_page == 1
    assert page.total == 5
    assert len(page.items) == 2
    assert page.last_page == 3
