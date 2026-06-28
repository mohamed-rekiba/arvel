"""Queues (doc 12) — Bus.chain/batch + job-instance serialization. Test-first."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.queue import Bus, Job, deserialize_instance, serialize_instance


class Gadget(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]


class Encode(Job):
    def __init__(self, gadget: Gadget, *, level: int = 1) -> None:
        self.gadget = gadget
        self.level = level

    async def handle(self) -> None: ...


class Noop(Job):
    async def handle(self) -> None: ...


class RecordingManager:
    """Stands in for the queue manager; records the order jobs are pushed."""

    def __init__(self) -> None:
        self.pushed: list[Any] = []

    async def push_instance(self, job: Any, *, queue: str | None = None) -> Any:
        self.pushed.append(job)
        return job


async def test_instance_serialize_roundtrip_with_model_ref() -> None:
    db = ConnectionResolver()
    Gadget.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Gadget.__table__))
        gadget = await Gadget.create(name="widget")

        payload = serialize_instance(Encode(gadget, level=5))
        assert "widget" not in payload  # model state is a ref, not inlined

        job = await deserialize_instance(payload)
        assert isinstance(job, Encode)
        assert isinstance(job.gadget, Gadget)
        assert job.gadget.id == gadget.id
        assert job.gadget.name == "widget"  # re-fetched
        assert job.level == 5
    finally:
        await db.dispose()


async def test_bus_chain_dispatches_in_order() -> None:
    rec = RecordingManager()
    a, b, c = Noop(), Noop(), Noop()
    await Bus.chain([a, b, c]).dispatch(manager=rec)
    assert rec.pushed == [a, b, c]


async def test_bus_batch_dispatches_all() -> None:
    rec = RecordingManager()
    jobs = [Noop(), Noop(), Noop()]
    await Bus.batch(jobs).dispatch(manager=rec)
    assert {id(j) for j in rec.pushed} == {id(j) for j in jobs}
