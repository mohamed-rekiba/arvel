"""Queues (doc 12) — model-ref serialization: dispatch stores (class, pk); worker re-fetches."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.queue import Job, deserialize, serialize

processed: list[str] = []


class Widget(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]


class ProcessWidget(Job):
    def __init__(self, widget: Widget, *, note: str = "") -> None:
        self.widget = widget
        self.note = note

    async def handle(self) -> None:
        processed.append(f"{self.widget.name}:{self.note}")


async def test_model_serialized_as_ref_and_refetched() -> None:
    db = ConnectionResolver()
    Widget.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Widget.__table__))
        widget = await Widget.create(name="gadget")

        payload = serialize(ProcessWidget, (widget,), {"note": "hi"})
        assert "gadget" not in payload  # the row data is NOT in the payload — only a ref
        assert str(widget.id) in payload

        job = await deserialize(payload)  # worker side: re-fetch the model
        assert isinstance(job, ProcessWidget)
        assert isinstance(job.widget, Widget)
        assert job.widget.id == widget.id
        assert job.widget.name == "gadget"  # freshly fetched from the DB
        assert job.note == "hi"

        await job.handle()
        assert processed == ["gadget:hi"]
    finally:
        await db.dispose()


class JustNumbers(Job):
    def __init__(self, a: int, b: int) -> None:
        self.total = a + b

    async def handle(self) -> None: ...


async def test_plain_args_still_roundtrip() -> None:
    payload = serialize(JustNumbers, (2, 3), {})
    job = await deserialize(payload)
    assert isinstance(job, JustNumbers)
    assert job.total == 5
