"""Job base class — Pydantic BaseModel with handle() and auto-registration (ADR-033).

WI-018 added ``delay`` and ``priority`` as first-class fields (ADR-066). Both
are envelope metadata, not job state, so they're excluded from the JSON
payload that travels through the broker.
"""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from arvel.queue.envelope import JobEnvelope


class Job(BaseModel):
    """Base class for all queued jobs.

    Subclasses declare payload fields as Pydantic fields and implement ``handle()``.
    Subclasses are automatically registered in ``JobRegistry`` via ``__init_subclass__``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    queue: str = "default"
    tries: int = 3
    timeout: int = 60
    # ADR-066: delay accepts int (seconds) or timedelta; normalised to int at envelope time.
    delay: int | timedelta = 0
    # ADR-066: priority is 0..9; out-of-range rejected at instantiation.
    priority: int = Field(default=0, ge=0, le=9)
    # Seconds to wait before retry; list means per-attempt delays (e.g. [30, 60, 120]).
    backoff: int | list[int] = 0
    # Hard deadline for retries — jobs past this datetime go straight to DLQ.
    retry_until: datetime | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        from arvel.queue.registry import JobRegistry

        key = f"{cls.__module__}.{cls.__qualname__}"
        JobRegistry[key] = cls

    @abstractmethod
    async def handle(self) -> None:
        """Execute the job. Implemented by every concrete subclass."""

    def backoff_for(self, attempt: int) -> int:
        """Return the delay in seconds for the given attempt number (1-based)."""
        b = self.backoff
        if isinstance(b, list):
            idx = min(attempt - 1, len(b) - 1)
            return b[idx] if b else 0
        return int(b)

    def to_envelope(self) -> JobEnvelope:
        """Serialize this job to its wire format.

        ``queue``, ``timeout``, ``delay``, and ``priority`` are envelope metadata
        and are excluded from the payload. ``delay`` is normalised to int seconds.
        """
        key = f"{type(self).__module__}.{type(self).__qualname__}"
        payload = self.model_dump(
            exclude={"queue", "timeout", "delay", "priority", "backoff", "retry_until"}
        )
        delay_seconds = (
            int(self.delay.total_seconds())
            if isinstance(self.delay, timedelta)
            else int(self.delay)
        )
        return JobEnvelope(
            job_class=key,
            payload=payload,
            delay=delay_seconds,
            priority=int(self.priority),
        )


__all__ = ["Job"]
