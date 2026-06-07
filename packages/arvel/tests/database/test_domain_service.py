"""``DomainService.get_for_write()`` — read/write split with FOR UPDATE lock."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import DB, Model, column, string
from arvel.database.domain import DomainService
from arvel.database.exceptions import (
    OutsideTransactionError,
    ReadModelNotFoundError,
)
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


# Explicit string PKs so the same `pk` value addresses rows in both tables.
class _ReadThing(Model):
    __tablename__ = "domain_svc_read_things"
    id: str = column(String(36), primary_key=True)
    title: str = string(200)


class _WriteThing(Model):
    __tablename__ = "domain_svc_write_things"
    id: str = column(String(36), primary_key=True)
    title: str = string(200)


class _ThingService(DomainService["_ReadThing", "_WriteThing"]):
    read_model = _ReadThing
    write_model = _WriteThing


async def _create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_raises_outside_transaction_when_no_session_bound() -> None:
    # No `session` fixture — the active-session ContextVar is unset.
    with pytest.raises(OutsideTransactionError):
        await _ThingService.get_for_write("anything")


async def test_raises_when_read_model_row_is_missing(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _create_tables(engine)

    with pytest.raises(ReadModelNotFoundError) as exc:
        await _ThingService.get_for_write("missing-pk")

    assert exc.value.read_model_name == "_ReadThing"
    assert exc.value.key == "missing-pk"


async def test_raises_when_write_row_is_missing_despite_read_row_present(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _create_tables(engine)
    # Read row exists, write row does not — materialized-view-lag scenario.
    await _ReadThing.create(id="orphan", title="ghost")

    with pytest.raises(ReadModelNotFoundError) as exc:
        await _ThingService.get_for_write("orphan")

    # Second-stage error reports the write-side name so ops can grep.
    assert exc.value.read_model_name == "_WriteThing"


async def test_returns_locked_write_row_on_happy_path(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _create_tables(engine)
    await _ReadThing.create(id="pk-7", title="visible")
    await _WriteThing.create(id="pk-7", title="authoritative")

    locked: Any = await _ThingService.get_for_write("pk-7")

    assert isinstance(locked, _WriteThing)
    assert locked.id == "pk-7"
    assert locked.title == "authoritative"


async def test_works_inside_db_transaction_block(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _create_tables(engine)
    await _ReadThing.create(id="pk-11", title="r")
    await _WriteThing.create(id="pk-11", title="w")

    async with DB.transaction():
        locked: Any = await _ThingService.get_for_write("pk-11")
        assert locked.id == "pk-11"
