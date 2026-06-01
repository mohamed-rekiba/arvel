"""Distinct soft/hard-delete + replicate events.

- ``trashed`` fires on a soft delete (alongside ``deleted``), never on a hard delete.
- ``force_deleting`` / ``force_deleted`` fire on ``force_delete``; ``trashed`` does not.
- ``replicating`` fires on the fresh clone returned by ``replicate``.

Each model gets its own observer list so ``clear_observers`` stays isolated."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, Observer, SoftDeletes, Timestamps, id_, string
from arvel.database.events import clear_observers
from arvel.database.exceptions import OperationCancelledError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class Wi023Soft(Model, Timestamps, SoftDeletes):
    __tablename__ = "wi023_soft"
    id: int = id_()
    name: str = string(100)


class Wi023Hard(Model):
    __tablename__ = "wi023_hard"
    id: int = id_()
    name: str = string(100)


class _Recorder(Observer[Any]):
    def __init__(self) -> None:
        self.seen: list[str] = []

    def deleted(self, _m: Any) -> None:
        self.seen.append("deleted")

    def trashed(self, _m: Any) -> None:
        self.seen.append("trashed")

    def force_deleting(self, _m: Any) -> None:
        self.seen.append("force_deleting")

    def force_deleted(self, _m: Any) -> None:
        self.seen.append("force_deleted")

    def replicating(self, m: Any) -> None:
        self.seen.append(f"replicating:{m.name}")


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestSoftDeleteEvents:
    async def test_trashed_fires_on_soft_delete(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        clear_observers(Wi023Soft)
        rec = _Recorder()
        Wi023Soft.observe(rec)
        row = await Wi023Soft.create(name="a")
        await row.delete()
        # Both fire, in order: trashed then deleted. force_* never fire.
        assert rec.seen == ["trashed", "deleted"]

    async def test_force_delete_fires_force_events_not_trashed(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        clear_observers(Wi023Soft)
        rec = _Recorder()
        Wi023Soft.observe(rec)
        row = await Wi023Soft.create(name="b")
        await row.force_delete()
        assert rec.seen == ["force_deleting", "deleted", "force_deleted"]
        assert "trashed" not in rec.seen

    async def test_force_deleting_can_abort(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        clear_observers(Wi023Soft)
        Wi023Soft.on("force_deleting", lambda _m: False)
        row = await Wi023Soft.create(name="c")
        with pytest.raises(OperationCancelledError):
            await row.force_delete()


class TestHardDeleteEvents:
    async def test_plain_delete_fires_deleted_only(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        clear_observers(Wi023Hard)
        rec = _Recorder()
        Wi023Hard.observe(rec)
        row = await Wi023Hard.create(name="x")
        await row.delete()
        assert rec.seen == ["deleted"]


class TestReplicatingEvent:
    async def test_replicating_fires_on_clone(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        clear_observers(Wi023Hard)
        rec = _Recorder()
        Wi023Hard.observe(rec)
        row = await Wi023Hard.create(name="orig")
        clone = await row.replicate()
        assert clone.name == "orig"
        assert rec.seen == ["replicating:orig"]
