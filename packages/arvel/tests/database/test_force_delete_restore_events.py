"""force_delete() and restore() fire observer hooks; replicate() drops timestamps.

Eloquent fires deleting/deleted on forceDelete and restoring/restored on restore,
and a replicated model starts without timestamps or a soft-delete flag.
"""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, Observer, SoftDeletes, Timestamps
from arvel.database.events import clear_observers
from arvel.database.exceptions import OperationCancelledError
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class Paper(Model, Timestamps, SoftDeletes):
    __tablename__ = "fdr_papers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(120))


class Recorder(Observer[Paper]):
    def __init__(self) -> None:
        self.events: list[str] = []

    def deleting(self, instance: Paper) -> None:
        self.events.append("deleting")

    def deleted(self, instance: Paper) -> None:
        self.events.append("deleted")

    def restoring(self, instance: Paper) -> None:
        self.events.append("restoring")

    def restored(self, instance: Paper) -> None:
        self.events.append("restored")


class VetoRestore(Observer[Paper]):
    def restoring(self, instance: Paper) -> bool:
        return False


async def _setup(engine: AsyncEngine) -> None:
    clear_observers(Paper)
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_force_delete_fires_delete_events(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    rec = Recorder()
    Paper.observe(rec)
    paper = await Paper.create(title="x")

    await paper.force_delete()

    assert rec.events == ["deleting", "deleted"]


async def test_restore_fires_restore_events(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    rec = Recorder()
    Paper.observe(rec)
    paper = await Paper.create(title="x")
    await paper.delete()
    rec.events.clear()

    await paper.restore()

    assert rec.events == ["restoring", "restored"]
    assert paper.deleted_at is None


async def test_restoring_can_be_cancelled(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    Paper.observe(VetoRestore())
    paper = await Paper.create(title="x")
    await paper.delete()

    with pytest.raises(OperationCancelledError):
        await paper.restore()
    assert paper.deleted_at is not None


async def test_replicate_drops_timestamps_and_soft_delete(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    paper = await Paper.create(title="original")
    await paper.delete()  # sets deleted_at

    clone: Any = await paper.replicate()

    assert clone.title == "original"
    assert clone.id is None
    assert clone.deleted_at is None
