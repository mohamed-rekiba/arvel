"""Bus — dispatch and chain operations for queued jobs.

Per-dispatch ``delay`` and ``priority`` keyword overrides. ``None`` means
"use the value already on the ``Job`` instance".

``chain`` is the real one — successor jobs are encoded on the head envelope
and dispatched by the worker only after each predecessor finishes successfully.
A failed link ends the chain.

``dispatch_many`` is fan-out: every job is pushed independently, no ordering.
Use it instead of an imagined ``batch`` API; real batch tracking (BatchId,
progress, then/catch/finally callbacks) is a future feature.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from arvel.queue.envelope import ChainStep
from arvel.queue.job import Job
from arvel.queue.manager import QueueManager


class Bus:
    """Central dispatch point for queued jobs."""

    def __init__(self, manager: QueueManager) -> None:
        self._manager = manager

    async def dispatch(
        self,
        job: Job,
        *,
        connection: str | None = None,
        delay: int | timedelta | None = None,
        priority: int | None = None,
    ) -> None:
        """Dispatch a single job. ``None`` overrides mean 'use the value on the Job'."""
        if delay is not None:
            job.delay = delay
        if priority is not None:
            job.priority = priority
        await self._manager.push(job, queue=None)

    async def dispatch_many(self, jobs: Sequence[Job]) -> None:
        """Dispatch every job independently. No ordering, no inter-job state."""
        for job in jobs:
            await self._manager.push(job)

    async def chain(self, jobs: Sequence[Job]) -> None:
        """Dispatch ``jobs`` so that each runs only after the previous succeeds.

        The first job is enqueued now; the remaining jobs travel along on the
        head envelope's ``chain`` field. After each link's ``handle()`` returns
        cleanly, the worker pops the next ``ChainStep`` and enqueues it. A link
        that exhausts its retries (lands in the DLQ) ends the chain — no
        further successors are dispatched.
        """
        if not jobs:
            return
        head_job = jobs[0]
        head_envelope = head_job.to_envelope()
        for tail_job in jobs[1:]:
            tail_envelope = tail_job.to_envelope()
            head_envelope.chain.append(
                ChainStep(
                    job_class=tail_envelope.job_class,
                    payload=tail_envelope.payload,
                    queue=tail_job.queue,
                    delay=tail_envelope.delay,
                    priority=tail_envelope.priority,
                )
            )
        conn = self._manager.connection()
        await conn.push(head_envelope, queue=head_job.queue)


__all__ = ["Bus"]
