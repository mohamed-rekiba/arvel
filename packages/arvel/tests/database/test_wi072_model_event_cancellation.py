"""Cancellable creating/updating/deleting hooks."""

from __future__ import annotations

import pytest
from arvel.database import Model, Observer, id_, string
from arvel.database.events import clear_observers
from arvel.database.exceptions import OperationCancelledError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class Wi072Note(Model):
    __tablename__ = "wi072_notes"
    id: int = id_()
    body: str = string(200)


async def _setup(engine: AsyncEngine) -> None:
    clear_observers(Wi072Note)
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def _count_notes(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(Wi072Note))
    return int(result.scalar_one())


class TestUpdatedDeletedEvents:
    async def test_updated_fires_on_existing_record_save(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        events: list[str] = []

        class Hook(Observer[Wi072Note]):
            def updating(self, instance: Wi072Note) -> None:
                events.append(f"updating:{instance.body}")

            def updated(self, instance: Wi072Note) -> None:
                events.append(f"updated:{instance.body}")

        Wi072Note.observe(Hook())
        note = await Wi072Note.create(body="draft")
        note.body = "published"
        await note.save()

        assert "updating:published" in events
        assert "updated:published" in events

    async def test_deleted_fires_on_hard_delete(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        events: list[str] = []

        class Hook(Observer[Wi072Note]):
            def deleting(self, instance: Wi072Note) -> None:
                events.append(f"deleting:{instance.body}")

            def deleted(self, instance: Wi072Note) -> None:
                events.append(f"deleted:{instance.body}")

        Wi072Note.observe(Hook())
        note = await Wi072Note.create(body="gone")
        await note.delete()

        assert "deleting:gone" in events
        assert "deleted:gone" in events


class TestCancellableBeforeHooks:
    async def test_creating_false_aborts_insert(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)

        class Block(Observer[Wi072Note]):
            def creating(self, instance: Wi072Note) -> bool:
                return False

        Wi072Note.observe(Block())

        with pytest.raises(OperationCancelledError) as exc:
            await Wi072Note.create(body="blocked")

        assert exc.value.event_name == "creating"
        assert await _count_notes(session) == 0

    async def test_updating_false_aborts_save(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        note = await Wi072Note.create(body="keep")

        class Block(Observer[Wi072Note]):
            def updating(self, instance: Wi072Note) -> bool:
                return False

        Wi072Note.observe(Block())
        note.body = "mutated"

        with session.no_autoflush, pytest.raises(OperationCancelledError) as exc:
            await note.save()

        assert exc.value.event_name == "updating"
        result = await session.execute(
            select(Wi072Note.__table__.c.body).where(Wi072Note.__table__.c.id == note.id),
            execution_options={"autoflush": False},
        )
        assert result.scalar_one() == "keep"

    async def test_deleting_false_aborts_delete(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        note = await Wi072Note.create(body="stay")

        class Block(Observer[Wi072Note]):
            def deleting(self, instance: Wi072Note) -> bool:
                return False

        Wi072Note.observe(Block())

        with pytest.raises(OperationCancelledError) as exc:
            await note.delete()

        assert exc.value.event_name == "deleting"
        assert await _count_notes(session) == 1

    async def test_async_creating_false_aborts_insert(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)

        class AsyncBlock(Observer[Wi072Note]):
            async def creating(self, instance: Wi072Note) -> bool:
                return False

        Wi072Note.observe(AsyncBlock())

        with pytest.raises(OperationCancelledError):
            await Wi072Note.create(body="async-blocked")

        assert await _count_notes(session) == 0
