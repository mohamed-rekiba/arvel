"""Job base class — all queue jobs inherit from this."""

from datetime import (
    timedelta,  # noqa: TC003 — Pydantic needs this at runtime for field type resolution
)

from pydantic import BaseModel, ConfigDict


class Job(BaseModel):
    """Base class for background jobs.

    Subclass and implement ``handle()``. Configure retries, backoff,
    timeout, and middleware by overriding the class attributes or
    the ``middleware()`` method.

    Backoff accepts three forms:
    - ``int``: fixed delay in seconds between every retry
    - ``list[int]``: per-attempt delays (last value repeats for overflow)
    - ``"exponential"``: uses ``backoff_base ** attempt`` seconds
    """

    model_config = ConfigDict(frozen=False)

    max_retries: int = 3
    backoff: int | list[int] | str = 60
    backoff_base: int = 2
    timeout_seconds: int = 300
    queue_name: str = "default"
    max_exceptions: int | None = None
    retry_until: timedelta | None = None

    unique_for: int | None = None
    unique_id: str | None = None
    unique_until_processing: bool = False

    async def handle(self) -> None:
        """Execute the job's work. Override in subclasses."""
        raise NotImplementedError

    async def on_failure(self, error: Exception) -> None:
        """Called when the job fails permanently (retries exhausted)."""

    def middleware(self) -> list[object]:
        """Return middleware instances to wrap this job's execution."""
        return []

    def get_unique_id(self) -> str:
        """Return the uniqueness key for this job. Override for custom keys."""
        return self.unique_id or f"{type(self).__name__}"
