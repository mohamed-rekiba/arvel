"""QueueFake — testing double for QueueContract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.queue.contracts import QueueContract

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import timedelta

    from arvel.queue.job import Job


class QueueFake(QueueContract):
    """Captures dispatched jobs for test assertions.

    Use in tests to replace the real queue driver and verify
    that jobs were dispatched with expected payloads.
    """

    def __init__(self) -> None:
        self._jobs: list[Job] = []

    @property
    def pushed_count(self) -> int:
        return len(self._jobs)

    async def dispatch(self, job: Job) -> None:
        self._jobs.append(job)

    async def later(self, delay: timedelta, job: Job) -> None:
        self._jobs.append(job)

    async def bulk(self, jobs: Sequence[Job]) -> None:
        self._jobs.extend(jobs)

    async def size(self, queue_name: str = "default") -> int:
        return len([j for j in self._jobs if j.queue_name == queue_name])

    def assert_pushed(self, job_type: type[Job]) -> None:
        matches = [j for j in self._jobs if isinstance(j, job_type)]
        if not matches:
            msg = f"Expected {job_type.__name__} to be pushed, but it wasn't"
            raise AssertionError(msg)

    def assert_pushed_with(self, job_type: type[Job], **kwargs: Any) -> None:
        for job in self._jobs:
            if not isinstance(job, job_type):
                continue
            data = job.model_dump()
            if all(data.get(k) == v for k, v in kwargs.items()):
                return
        msg = f"Expected {job_type.__name__} with {kwargs} to be pushed, but no match found"
        raise AssertionError(msg)

    def assert_pushed_on(self, queue_name: str, job_type: type[Job]) -> None:
        matches = [j for j in self._jobs if isinstance(j, job_type) and j.queue_name == queue_name]
        if not matches:
            msg = f"Expected {job_type.__name__} on queue '{queue_name}', but none found"
            raise AssertionError(msg)

    def assert_pushed_count(self, job_type: type[Job], expected: int) -> None:
        actual = len([j for j in self._jobs if isinstance(j, job_type)])
        if actual != expected:
            msg = f"Expected {expected} {job_type.__name__} jobs, but got {actual}"
            raise AssertionError(msg)

    def assert_nothing_pushed(self) -> None:
        if self._jobs:
            types = {type(j).__name__ for j in self._jobs}
            msg = f"Expected no jobs pushed, but got {len(self._jobs)}: {types}"
            raise AssertionError(msg)
