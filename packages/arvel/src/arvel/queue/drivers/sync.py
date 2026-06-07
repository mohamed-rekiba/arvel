"""Sync driver — executes jobs inline in the calling coroutine.

Honours ``envelope.delay`` via ``asyncio.sleep`` before executing ``handle``.
Priority is a documented no-op (single in-flight job). Chain successors run
inline too — a chain link that raises ends the chain right there, which
matches the worker's DLQ-driven stop-on-failure semantics.
"""

from __future__ import annotations

import asyncio

from arvel.queue.envelope import JobEnvelope
from arvel.queue.registry import deserialize_job


class SyncConnection:
    """Executes jobs immediately, in-process. Zero setup. Default for development and tests."""

    async def push(self, envelope: JobEnvelope, queue: str = "default") -> None:
        if envelope.delay > 0:
            await asyncio.sleep(envelope.delay)
        job = deserialize_job(envelope)
        await job.handle()
        for step in envelope.chain:
            successor = JobEnvelope(
                job_class=step.job_class,
                payload=step.payload,
                delay=step.delay,
                priority=step.priority,
            )
            await self.push(successor, queue=step.queue)

    async def pop_blocking(
        self, queue: str = "default", timeout: float = 3.0
    ) -> JobEnvelope | None:
        return None

    async def size(self, queue: str = "default") -> int:
        return 0

    async def clear(self, queue: str = "default") -> None:
        pass

    async def close(self) -> None:
        pass


__all__ = ["SyncConnection"]
