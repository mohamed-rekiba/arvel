"""FR-003-025..027 — Lifecycle events and observers."""

from __future__ import annotations

from typing import Any

from arvel.database import Model, Observer, id_, string
from arvel.database.events import clear_observers
from sqlalchemy.ext.asyncio import AsyncSession


class Note(Model):
    __tablename__ = "notes_o"
    id: int = id_()
    body: str = string(200)


class RecordingObserver(Observer[Note]):
    def __init__(self) -> None:
        self.events: list[str] = []

    def creating(self, instance: Note) -> None:
        self.events.append(f"creating:{instance.body}")

    def created(self, instance: Note) -> None:
        self.events.append(f"created:{instance.body}")

    def updating(self, instance: Note) -> None:
        self.events.append(f"updating:{instance.body}")

    def updated(self, instance: Note) -> None:
        self.events.append(f"updated:{instance.body}")

    def deleting(self, instance: Note) -> None:
        self.events.append(f"deleting:{instance.body}")

    def deleted(self, instance: Note) -> None:
        self.events.append(f"deleted:{instance.body}")


async def _setup(engine: Any) -> None:
    clear_observers(Note)
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_observer_fires_lifecycle_events(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    obs = RecordingObserver()
    Note.observe(obs)

    note = await Note.create(body="hi")
    note.body = "hello"
    await note.save()
    await note.delete()

    assert any(e.startswith("creating:") for e in obs.events)
    assert any(e.startswith("created:") for e in obs.events)
    assert any(e.startswith("updating:") for e in obs.events)
    assert any(e.startswith("updated:") for e in obs.events)
    assert any(e.startswith("deleting:") for e in obs.events)
    assert any(e.startswith("deleted:") for e in obs.events)
