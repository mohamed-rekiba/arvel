"""JobRunner — central job execution engine with retry, timeout, middleware, and context.

All queue drivers delegate to ``JobRunner.execute(job)`` for consistent
retry/backoff, timeout enforcement, middleware pipeline, and context propagation.
See ADR-019-001 for the design rationale.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import anyio

from arvel.context.context_store import Context
from arvel.queue.exceptions import JobMaxRetriesError, JobTimeoutError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from arvel.queue.job import Job
    from arvel.queue.middleware import JobMiddleware


class JobRunner:
    """Executes a job with retry logic, timeout, middleware pipeline, and context propagation.

    Args:
        middleware_overrides: If provided, these middleware run instead of ``job.middleware()``.
            Useful for testing and for drivers that inject middleware externally.
    """

    def __init__(
        self,
        middleware_overrides: list[JobMiddleware] | None = None,
    ) -> None:
        self._middleware_overrides = middleware_overrides

    async def execute(
        self,
        job: Job,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Run *job* through the middleware pipeline, then execute with retry/timeout.

        When *context* is provided, it's hydrated before ``handle()`` and flushed after.
        """
        middleware_list = (
            self._middleware_overrides
            if self._middleware_overrides is not None
            else job.middleware()
        )

        if middleware_list:
            await self._run_with_middleware(job, middleware_list, context)
        else:
            await self._execute_with_retries(job, context)

    async def _run_with_middleware(
        self,
        job: Job,
        middleware_list: list[JobMiddleware] | list[object],
        context: dict[str, Any] | None,
    ) -> None:
        """Build a middleware chain using a simple async pipeline."""
        from arvel.queue.middleware import JobMiddleware as _JobMiddleware

        async def final_handler(j: Job) -> None:
            await self._execute_with_retries(j, context)

        chain: Callable[[Job], Awaitable[None]] = final_handler
        for mw in reversed(middleware_list):
            if not isinstance(mw, _JobMiddleware):
                msg = f"Middleware must be a JobMiddleware instance, got {type(mw).__name__}"
                raise TypeError(msg)
            chain = _make_link(mw, chain)

        await chain(job)

    async def _execute_with_retries(
        self,
        job: Job,
        context: dict[str, Any] | None,
    ) -> None:
        """Core retry loop with timeout and context propagation."""
        delays = self._compute_backoff_delays(job)
        attempt = 0
        exception_count = 0
        start_time = time.monotonic()
        last_error: Exception | None = None
        max_attempts = 1 + job.max_retries

        while attempt < max_attempts:
            if self._should_stop_retrying(job, attempt, exception_count, start_time):
                break

            result = await self._try_once(job, context)
            if result is None:
                return  # success

            last_error = result
            exception_count += 1
            attempt += 1

            await self._backoff_delay(attempt, max_attempts, delays)

        if last_error is not None:
            await job.on_failure(last_error)

        raise JobMaxRetriesError(
            f"{type(job).__name__} failed after {attempt} attempt(s)",
            job_class=type(job).__name__,
            attempts=attempt,
        )

    def _should_stop_retrying(
        self,
        job: Job,
        attempt: int,
        exception_count: int,
        start_time: float,
    ) -> bool:
        """Check deadline and exception-count early-exit conditions."""
        if job.retry_until is not None and attempt > 0:
            elapsed = time.monotonic() - start_time
            if elapsed >= job.retry_until.total_seconds():
                return True
        return job.max_exceptions is not None and exception_count >= job.max_exceptions

    async def _try_once(
        self,
        job: Job,
        context: dict[str, Any] | None,
    ) -> Exception | None:
        """Execute handle() once with context and timeout. Returns None on success."""
        try:
            if context is not None:
                Context.hydrate(context)

            if job.timeout_seconds > 0:
                with anyio.fail_after(job.timeout_seconds):
                    await job.handle()
            else:
                await job.handle()

            return None
        except TimeoutError:
            return JobTimeoutError(
                f"{type(job).__name__} timed out after {job.timeout_seconds}s",
                job_class=type(job).__name__,
                timeout=job.timeout_seconds,
            )
        except Exception as exc:
            return exc
        finally:
            if context is not None:
                Context.flush()

    @staticmethod
    async def _backoff_delay(attempt: int, max_attempts: int, delays: list[int]) -> None:
        if attempt < max_attempts and delays:
            delay_idx = min(attempt - 1, len(delays) - 1)
            delay = delays[delay_idx]
            if delay > 0:
                await anyio.sleep(delay)

    def _compute_backoff_delays(self, job: Job) -> list[int]:
        """Compute the delay sequence for all retry attempts."""
        count = job.max_retries
        if count <= 0:
            return []

        backoff = job.backoff

        if isinstance(backoff, int):
            return [backoff] * count

        if isinstance(backoff, list):
            if not backoff:
                return [0] * count
            result: list[int] = []
            for i in range(count):
                idx = min(i, len(backoff) - 1)
                result.append(backoff[idx])
            return result

        if backoff == "exponential":
            base = job.backoff_base
            return [base ** (i + 1) for i in range(count)]

        return [0] * count


def _make_link(
    mw: JobMiddleware,
    next_call: Callable[[Job], Awaitable[None]],
) -> Callable[[Job], Awaitable[None]]:
    """Wrap a middleware + next into a single async callable."""

    async def link(job: Job) -> None:
        await mw.handle(job, next_call)

    return link
