"""QueueConnection Protocol — implemented by every driver."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from arvel.queue.envelope import JobEnvelope


@runtime_checkable
class QueueConnection(Protocol):
    """Structural interface every queue driver must satisfy."""

    async def push(self, envelope: JobEnvelope, queue: str = "default") -> None: ...

    async def pop_blocking(
        self, queue: str = "default", timeout: float = 3.0
    ) -> JobEnvelope | None: ...

    async def size(self, queue: str = "default") -> int: ...

    async def clear(self, queue: str = "default") -> None: ...

    async def close(self) -> None: ...


__all__ = ["QueueConnection"]
