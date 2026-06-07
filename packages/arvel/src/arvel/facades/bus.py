"""Bus facade — @classmethod API proxying to the bound QueueManager."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from arvel.queue.exceptions import FacadeNotBoundError

if TYPE_CHECKING:
    from arvel.container import Container
    from arvel.queue.job import Job
    from arvel.queue.manager import QueueManager
    from arvel.testing.fakes.bus import BusFake, BusFakeContext


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
    async def dispatch_many(cls, jobs: list[Job]) -> None:
        from arvel.queue.bus import Bus as _BusImpl

        bus = _BusImpl(cls.mgr())
        await bus.dispatch_many(jobs)

    @classmethod
    async def chain(cls, jobs: list[Job]) -> None:
        from arvel.queue.bus import Bus as _BusImpl

        bus = _BusImpl(cls.mgr())
        await bus.chain(jobs)

    @classmethod
    def fake(cls) -> BusFakeContext:
        """Swap in a ``BusFake`` recorder for tests. Use as a context manager."""
        from arvel.testing.fakes.bus import BusFakeContext

        return BusFakeContext()

    @classmethod
    def _active_fake(cls, action: str) -> BusFake:
        from arvel.testing.fakes.bus import BusFake

        conn = cls.mgr().connection()
        if not isinstance(conn, BusFake):
            raise TypeError(f"Bus.{action} requires Bus.fake() context")
        return conn

    @classmethod
    def assert_dispatched(cls, job_class: type[Job], times: int | None = None) -> None:
        """Assert a job of ``job_class`` was dispatched (optionally N times)."""
        fake = cls._active_fake("assert_dispatched")
        matching = fake.pushed_of(job_class)
        if not matching:
            raise AssertionError(f"Job {job_class.__qualname__!r} was not dispatched")
        if times is not None and len(matching) != times:
            raise AssertionError(
                f"Job {job_class.__qualname__!r}: expected {times} dispatches, got {len(matching)}"
            )

    @classmethod
    def assert_not_dispatched(cls, job_class: type[Job]) -> None:
        """Assert that NO job of ``job_class`` was dispatched."""
        fake = cls._active_fake("assert_not_dispatched")
        matching = fake.pushed_of(job_class)
        if matching:
            raise AssertionError(
                f"Job {job_class.__qualname__!r} was dispatched {len(matching)} time(s)"
            )

    @classmethod
    def assert_dispatched_on(cls, job_class: type[Job], queue: str) -> None:
        """Assert ``job_class`` was dispatched onto ``queue`` at least once."""
        fake = cls._active_fake("assert_dispatched_on")
        matching = [p for p in fake.pushed_of(job_class) if p.queue == queue]
        if not matching:
            raise AssertionError(
                f"Job {job_class.__qualname__!r} was not dispatched on queue {queue!r}"
            )

    @classmethod
    def assert_chained(cls, head: type[Job], *tail: type[Job]) -> None:
        """Assert ``head`` was dispatched as the head of a chain ending in ``tail``.

        Walks the head envelope's ``chain`` and matches successor class names in
        order. Fails if no head was dispatched, or no chain matches.
        """
        from arvel.testing.fakes.bus import job_class_key

        fake = cls._active_fake("assert_chained")
        heads = fake.pushed_of(head)
        if not heads:
            raise AssertionError(f"Chain head {head.__qualname__!r} was not dispatched")
        expected = [job_class_key(t) for t in tail]
        for pushed in heads:
            actual = [step.job_class for step in pushed.envelope.chain]
            if actual == expected:
                return
        names = [t.__qualname__ for t in tail]
        raise AssertionError(f"No dispatched {head.__qualname__!r} had chain {names!r}")


__all__ = ["Bus"]
