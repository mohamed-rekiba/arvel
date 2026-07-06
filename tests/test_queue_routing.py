"""Per-class queue routing: one central registry, one label resolver for every enqueue path.
Precedence: explicit queue= > class-declared queue > registry > "default"."""

from __future__ import annotations

from typing import Any

from taskiq import InMemoryBroker

from arvel.queue import Job, QueueManager

RAN: list[str] = []


class CapturingBroker(InMemoryBroker):
    """Records every kicked message so tests can observe the queue label the broker saw."""

    def __init__(self) -> None:
        super().__init__()
        self.kicked: list[Any] = []

    async def kick(self, message: Any) -> None:
        self.kicked.append(message)
        await super().kick(message)


def _manager() -> tuple[QueueManager, CapturingBroker]:
    broker = CapturingBroker()
    return QueueManager(broker=broker), broker


def _label(broker: CapturingBroker) -> str:
    return str(broker.kicked[-1].labels.get("queue"))


class PlainJob(Job):  # inherits Job.queue — must NOT shadow the registry
    def __init__(self, value: str = "x") -> None:
        self.value = value

    async def handle(self) -> None:
        RAN.append(self.value)


class DeclaredJob(Job):
    queue = "declared"

    async def handle(self) -> None:
        RAN.append("declared")


async def test_registry_routes_a_bare_dispatch() -> None:
    manager, broker = _manager()
    manager.route(PlainJob, queue="reports")
    try:
        await manager.push(PlainJob, (), {})
        assert _label(broker) == "reports"
    finally:
        if manager._started:
            await manager.broker.shutdown()


async def test_class_declared_queue_beats_registry() -> None:
    manager, broker = _manager()
    manager.route(DeclaredJob, queue="routed")
    try:
        await manager.push(DeclaredJob, (), {})
        assert _label(broker) == "declared"
    finally:
        if manager._started:
            await manager.broker.shutdown()


async def test_explicit_argument_beats_everything() -> None:
    manager, broker = _manager()
    manager.route(DeclaredJob, queue="routed")
    try:
        await manager.push(DeclaredJob, (), {}, queue="explicit")
        assert _label(broker) == "explicit"
    finally:
        if manager._started:
            await manager.broker.shutdown()


async def test_last_registration_wins() -> None:
    manager, broker = _manager()
    manager.route(PlainJob, queue="first")
    manager.route(PlainJob, queue="second")
    try:
        await manager.push(PlainJob, (), {})
        assert _label(broker) == "second"
    finally:
        if manager._started:
            await manager.broker.shutdown()


async def test_push_instance_resolves_identically() -> None:
    manager, broker = _manager()
    manager.route(PlainJob, queue="reports")
    try:
        await manager.push_instance(PlainJob("y"))
        assert _label(broker) == "reports"
    finally:
        if manager._started:
            await manager.broker.shutdown()


async def test_unrouted_inherited_queue_defaults() -> None:
    manager, broker = _manager()
    try:
        await manager.push(PlainJob, (), {})
        assert _label(broker) == "default"
    finally:
        if manager._started:
            await manager.broker.shutdown()


class GrandchildJob(DeclaredJob):  # inherits the parent's DECLARED queue
    pass


async def test_parent_declared_queue_beats_registry_for_grandchild() -> None:
    # a declaration anywhere below the Job base is the class's own voice; the registry is
    # only the fallback for classes that never declared one
    manager, broker = _manager()
    manager.route(GrandchildJob, queue="routed")
    try:
        await manager.push(GrandchildJob, (), {})
        assert _label(broker) == "declared"
    finally:
        if manager._started:
            await manager.broker.shutdown()


async def test_delayed_dispatch_persists_the_routed_queue() -> None:
    # the durable path (dispatch_after → jobs table → release) must resolve through the
    # registry too — a routed class may not silently retry on "default"
    import sqlalchemy as sa

    from arvel.database import ConnectionResolver
    from arvel.kernel import Application, set_application
    from arvel.queue import QueuedJob

    app = Application()
    db = ConnectionResolver()
    app.instance("db", db)
    manager, _broker = _manager()
    app.instance("queue", manager)
    set_application(app)
    QueuedJob.set_connection(db)
    await db.execute(sa.schema.CreateTable(QueuedJob.__table__))
    try:
        manager.route(PlainJob, queue="reports")
        await manager.dispatch_after(3600, PlainJob("later"))
        rows = await QueuedJob.all()
        assert [r.queue for r in rows] == ["reports"]
    finally:
        set_application(None)
        if manager._started:
            await manager.broker.shutdown()
        await db.dispose()
