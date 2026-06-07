"""BusFake + Bus.fake/.assert_* — Laravel-style queue assertions for tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import TracebackType
from typing import TYPE_CHECKING, Self

from arvel.queue.envelope import JobEnvelope

if TYPE_CHECKING:
    from arvel.queue.connection import QueueConnection
    from arvel.queue.job import Job


@dataclass(frozen=True)
class PushedJob:
    """One recorded dispatch: the envelope plus its target queue."""

    envelope: JobEnvelope
    queue: str


@dataclass
class BusFake:
    """In-memory ``QueueConnection`` — records every push, executes nothing.

    Mirrors Laravel's ``Queue::fake()`` behavior. Chained successors stay on the
    head envelope's ``chain`` list so ``assert_chained(Head, Tail)`` works.
    """

    pushed: list[PushedJob] = field(default_factory=list[PushedJob])

    async def push(self, envelope: JobEnvelope, queue: str = "default") -> None:
        self.pushed.append(PushedJob(envelope, queue))

    async def pop_blocking(
        self, queue: str = "default", timeout: float = 3.0
    ) -> JobEnvelope | None:
        return None

    async def size(self, queue: str = "default") -> int:
        return sum(1 for p in self.pushed if p.queue == queue)

    async def clear(self, queue: str = "default") -> None:
        self.pushed = [p for p in self.pushed if p.queue != queue]

    async def close(self) -> None:
        return None

    def pushed_of(self, job_class: type[Job] | str) -> list[PushedJob]:
        key = job_class_key(job_class)
        return [p for p in self.pushed if p.envelope.job_class == key]


def job_class_key(job_class: type[Job] | str) -> str:
    """The canonical envelope key for a job class (or pass-through string)."""
    if isinstance(job_class, str):
        return job_class
    return f"{job_class.__module__}.{job_class.__qualname__}"


class BusFakeContext:
    """Context manager: swap the active queue connection with a ``BusFake``."""

    def __init__(self) -> None:
        self._previous: QueueConnection | None = None
        self.fake = BusFake()

    def __enter__(self) -> Self:
        from arvel.facades.bus import Bus

        self._previous = Bus.mgr().swap_connection(self.fake)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        from arvel.facades.bus import Bus

        Bus.mgr().restore_connection(self._previous)


__all__ = ["BusFake", "BusFakeContext", "PushedJob", "job_class_key"]
