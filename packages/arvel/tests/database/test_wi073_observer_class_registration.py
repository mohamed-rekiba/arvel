"""WI-arvel-073 — Epic 049 Story 9: Model.observe(ObserverClass) + container DI."""

from __future__ import annotations

from typing import Any

from arvel.container import Container
from arvel.database import Model, Observer, id_, string
from arvel.database.events import clear_observers, configure_observer_container
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class Wi073Note(Model):
    __tablename__ = "wi073_notes"
    id: int = id_()
    body: str = string(200)


async def _setup(engine: AsyncEngine) -> None:
    clear_observers(Wi073Note)
    configure_observer_container(None)
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class _RecordingObserver(Observer[Wi073Note]):
    def __init__(self) -> None:
        self.events: list[str] = []

    def created(self, instance: Wi073Note) -> None:
        self.events.append(f"created:{instance.body}")


class _Clock:
    def __init__(self) -> None:
        self.ticks = 0


class _InjectedObserver(Observer[Wi073Note]):
    def __init__(self, clock: _Clock) -> None:
        self.clock = clock

    def creating(self, instance: Wi073Note) -> None:
        self.clock.ticks += 1
        _ = instance


class _NoInitObserver(Observer[Wi073Note]):
    """Observer with no explicit __init__ — inherits only from Observer/Generic."""

    def created(self, instance: Wi073Note) -> None:
        _NoInitObserver.seen.append(instance.body)

    seen: list[str] = []


class TestObserveObserverClass:
    async def test_observe_class_without_container_instantiates(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        Wi073Note.observe(_RecordingObserver)
        note = await Wi073Note.create(body="via-class")

        observers: list[Any] = Wi073Note._arvel_observers
        assert len(observers) == 1
        assert isinstance(observers[0], _RecordingObserver)
        assert observers[0].events == ["created:via-class"]
        assert note.body == "via-class"

    async def test_observe_class_resolves_from_container(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        container = Container()
        clock = _Clock()
        container.instance(_Clock, clock)
        configure_observer_container(container)

        Wi073Note.observe(_InjectedObserver)
        await Wi073Note.create(body="di")

        assert clock.ticks == 1

    async def test_observe_no_init_class_with_container_instantiates(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        # Regression: container refused no-__init__ observer classes with
        # BindingResolutionError; _resolve_observer must fall back to direct
        # instantiation instead of routing through container.make().
        await _setup(engine)
        _NoInitObserver.seen.clear()
        container = Container()
        configure_observer_container(container)

        Wi073Note.observe(_NoInitObserver)
        await Wi073Note.create(body="no-init")

        assert _NoInitObserver.seen == ["no-init"]

    async def test_observe_instance_still_works(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        obs = _RecordingObserver()
        Wi073Note.observe(obs)
        await Wi073Note.create(body="instance")

        assert obs.events == ["created:instance"]
