"""Auditable mixin auto-records create/update/delete with redaction and actor."""

from __future__ import annotations

import pytest
from arvel.context.facade import Context
from arvel.database.model import Model
from arvel_audit import REDACTED, AuditEntry
from arvel_audit.auditable import Auditable
from sqlalchemy import Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

pytestmark = pytest.mark.asyncio


class Widget(Model, Auditable):
    __tablename__ = "audit_widgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SecretCard(Model, Auditable):
    __tablename__ = "audit_secret_cards"
    __audit_redact__ = {"card_number", "cvv"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    card_number: Mapped[str] = mapped_column(String(32), nullable=False)
    cvv: Mapped[str] = mapped_column(String(8), nullable=False)
    holder: Mapped[str] = mapped_column(String(100), nullable=False, default="")


async def _entries(session: AsyncSession) -> list[AuditEntry]:
    result = await session.execute(select(AuditEntry).order_by(AuditEntry.id.asc()))
    return list(result.scalars().all())


async def test_created_records_full_new_values(tables: None, session: AsyncSession) -> None:
    widget = Widget(name="bolt", price=7)
    await widget.save()

    entries = await _entries(session)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.action == "created"
    assert entry.model_type == "Widget"
    assert entry.model_id == str(widget.id)
    assert entry.old_values == {}
    assert entry.new_values["name"] == "bolt"
    assert entry.new_values["price"] == 7


async def test_updated_records_changed_old_and_new(tables: None, session: AsyncSession) -> None:
    widget = Widget(name="bolt", price=7)
    await widget.save()
    widget.price = 9
    await widget.save()

    updated = [e for e in await _entries(session) if e.action == "updated"]
    assert len(updated) == 1
    assert updated[0].old_values == {"price": 7}
    assert updated[0].new_values == {"price": 9}


async def test_no_change_save_records_nothing(tables: None, session: AsyncSession) -> None:
    widget = Widget(name="bolt", price=7)
    await widget.save()
    await widget.save()  # nothing dirty

    assert [e.action for e in await _entries(session)] == ["created"]


async def test_deleted_records_last_values(tables: None, session: AsyncSession) -> None:
    widget = Widget(name="bolt", price=7)
    await widget.save()
    await widget.delete()

    deleted = [e for e in await _entries(session) if e.action == "deleted"]
    assert len(deleted) == 1
    assert deleted[0].new_values == {}
    assert deleted[0].old_values["name"] == "bolt"


async def test_redacted_fields_masked_in_both_directions(
    tables: None, session: AsyncSession
) -> None:
    card = SecretCard(card_number="4111111111111111", cvv="123", holder="Jo")
    await card.save()
    card.card_number = "4222222222222222"
    await card.save()

    entries = await _entries(session)
    created = next(e for e in entries if e.action == "created")
    assert created.new_values["card_number"] == REDACTED
    assert created.new_values["cvv"] == REDACTED
    assert created.new_values["holder"] == "Jo"

    updated = next(e for e in entries if e.action == "updated")
    assert updated.old_values["card_number"] == REDACTED
    assert updated.new_values["card_number"] == REDACTED


async def test_actor_pulled_from_context(tables: None, session: AsyncSession) -> None:
    Context.add("user_id", "user-42")
    widget = Widget(name="bolt", price=1)
    await widget.save()

    assert (await _entries(session))[0].actor_id == "user-42"


async def test_actor_none_without_context(tables: None, session: AsyncSession) -> None:
    widget = Widget(name="bolt", price=1)
    await widget.save()

    assert (await _entries(session))[0].actor_id is None
