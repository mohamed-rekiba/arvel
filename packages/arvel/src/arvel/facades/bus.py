"""Bus facade — @classmethod API proxying to the bound QueueManager."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from arvel.queue.exceptions import FacadeNotBoundError

if TYPE_CHECKING:
    from arvel.container import Container
    from arvel.queue.job import Job
    from arvel.queue.manager import QueueManager


class Bus:
    """Facade providing classmethod dispatch API for the queue subsystem.

    Bound by ``QueueServiceProvider.boot()``.
    """

    manager: ClassVar[QueueManager | None] = None

    @classmethod
    def bind(cls, container: Container) -> None:
        from arvel.queue.manager import QueueManager

        cls.manager = container.make(QueueManager)

    @classmethod
    def mgr(cls) -> QueueManager:
        if cls.manager is None:
            raise FacadeNotBoundError("Bus")
        return cls.manager

    @classmethod
    async def dispatch(cls, job: Job) -> None:
        from arvel.queue.bus import Bus as _BusImpl

        bus = _BusImpl(cls.mgr())
        await bus.dispatch(job)

    @classmethod
    async def batch(cls, jobs: list[Job]) -> None:
        from arvel.queue.bus import Bus as _BusImpl

        bus = _BusImpl(cls.mgr())
        await bus.batch(jobs)

    @classmethod
    async def chain(cls, jobs: list[Job]) -> None:
        from arvel.queue.bus import Bus as _BusImpl

        bus = _BusImpl(cls.mgr())
        await bus.chain(jobs)


__all__ = ["Bus"]
