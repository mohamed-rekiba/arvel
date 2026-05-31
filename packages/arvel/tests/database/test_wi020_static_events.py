"""WI-arvel-020 — Epic 006 Story 9: static event registration + custom event objects.

Three additions:
- ``Model.on("created", cb)`` — register a single callback, no observer class.
- ``__dispatches_events__`` — map a lifecycle name to a ``ModelEvent`` dispatched on the bus.
- ``__observed_by__`` — auto-register observer classes at class-definition time.

Each concern uses its own model so ``clear_observers`` in one test can't disturb another.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from arvel.database import Model, ModelEvent, Observer
from arvel.database.events import clear_observers
from arvel.database.exceptions import OperationCancelledError
from arvel.facades.event import Event
from arvel.testing.fakes.event import EventFake
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class Wi020Doc(Model):
    __tablename__ = "wi020_docs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(200), nullable=False)


class _AuditObserver(Observer["Wi020Observed"]):
    seen: ClassVar[list[str]] = []

    def created(self, instance: Wi020Observed) -> None:
        _AuditObserver.seen.append(instance.title)


class Wi020Observed(Model):
    __tablename__ = "wi020_observed"
    __observed_by__: ClassVar[list[type[Any]] | None] = [_AuditObserver]
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(200), nullable=False)


class Wi020EvtCreated(ModelEvent):
    pass


class Wi020Evt(Model):
    __tablename__ = "wi020_evt"
    __dispatches_events__: ClassVar[dict[str, type[Any]] | None] = {"created": Wi020EvtCreated}
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(200), nullable=False)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestModelOn:
    async def test_callback_runs_after_create(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        clear_observers(Wi020Doc)
        seen: list[str] = []
        Wi020Doc.on("created", lambda m: seen.append(m.title))
        await Wi020Doc.create(title="hello")
        assert seen == ["hello"]

    async def test_before_callback_can_abort(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        clear_observers(Wi020Doc)
        Wi020Doc.on("creating", lambda _m: False)
        with pytest.raises(OperationCancelledError):
            await Wi020Doc.create(title="blocked")

    async def test_async_callback_runs(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        clear_observers(Wi020Doc)
        seen: list[str] = []

        async def _cb(m: Wi020Doc) -> None:
            seen.append(m.title)

        Wi020Doc.on("created", _cb)
        await Wi020Doc.create(title="async")
        assert seen == ["async"]


class TestObservedBy:
    def test_observer_registered_at_class_definition(self) -> None:
        observers: list[Any] = Wi020Observed._arvel_observers
        assert any(isinstance(o, _AuditObserver) for o in observers)

    async def test_observer_fires_on_create(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        _AuditObserver.seen.clear()
        await Wi020Observed.create(title="observed")
        assert "observed" in _AuditObserver.seen


class TestDispatchesEvents:
    async def test_mapped_event_dispatched_on_bus(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        clear_observers(Wi020Evt)
        with Event.fake() as ctx:
            doc = await Wi020Evt.create(title="evt")
            fake: EventFake = ctx.fake
            dispatched = fake.dispatched_of(Wi020EvtCreated)
            assert len(dispatched) == 1
            assert dispatched[0].model is doc

    async def test_no_dispatch_when_bus_unbound(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        clear_observers(Wi020Evt)
        previous = Event.swap_dispatcher(None)
        try:
            doc = await Wi020Evt.create(title="quiet")
            assert doc.title == "quiet"
        finally:
            Event.swap_dispatcher(previous)
