"""Worker loop — polls the queue and executes jobs with retry + DLQ."""

from __future__ import annotations

import asyncio
import traceback
from datetime import UTC, datetime

from arvel.logging.facade import Log
from arvel.queue.envelope import JobEnvelope
from arvel.queue.manager import QueueManager
from arvel.queue.registry import deserialize_job
from arvel.queue.restart import QueueRestartSignal

logger = Log.channel(__name__)


class Worker:
    """Runs a continuous poll loop on a single queue until a stop event is set.

    On job failure:
    - increments ``envelope.attempts``
    - re-enqueues if ``attempts < job.tries``
    - routes to ``failed_job_store`` (DLQ) once ``attempts >= job.tries``

    On every loop iteration, polls :class:`QueueRestartSignal` (if provided)
    and exits gracefully when ``last_restart > self.started_at``.
    """

    def __init__(
        self,
        manager: QueueManager,
        queue: str = "default",
        sleep_interval: float = 3.0,
        failed_job_store: object | None = None,
        restart_signal: QueueRestartSignal | None = None,
    ) -> None:
        self._manager = manager
        self._queue = queue
        self._sleep_interval = sleep_interval
        self._failed_job_store = failed_job_store
        self._restart_signal = restart_signal
        self._started_at: datetime = datetime.now(UTC)
        self._jobs_processed: int = 0
        self._jobs_retried: int = 0
        self._jobs_dead: int = 0

    @property
    def started_at(self) -> datetime:
        return self._started_at

    @property
    def jobs_processed(self) -> int:
        return self._jobs_processed

    @property
    def jobs_retried(self) -> int:
        return self._jobs_retried

    @property
    def jobs_dead(self) -> int:
        return self._jobs_dead

    async def run_until(self, stop: asyncio.Event) -> None:
        """Poll and process jobs until ``stop`` is set."""
        conn = self._manager.connection()
        while not stop.is_set():
            if self._restart_signal is not None:
                last_restart = await self._restart_signal.last_restart()
                if last_restart is not None and last_restart > self._started_at:
                    stop.set()
                    break
            envelope = await conn.pop_blocking(queue=self._queue, timeout=self._sleep_interval)
            if envelope is None:
                await asyncio.sleep(self._sleep_interval)
                continue
            await self._process_one(envelope)

    async def drain_then_stop(self, *, poll_timeout: float = 0.1) -> None:
        """Process whatever is currently queued and exit when the queue drains.

        Used by ``queue:work --stop-when-empty`` for one-shot drains in CI or
        local debugging. Returns as soon as a poll comes back empty, never
        re-sleeps. ``poll_timeout`` controls how long each poll waits for an
        in-flight push before treating the queue as empty.
        """
        conn = self._manager.connection()
        while True:
            envelope = await conn.pop_blocking(queue=self._queue, timeout=poll_timeout)
            if envelope is None:
                return
            await self._process_one(envelope)

    async def _process_one(self, envelope: JobEnvelope) -> None:
        conn = self._manager.connection()
        job = deserialize_job(envelope)
        timeout = getattr(job, "timeout", 0)
        try:
            if timeout and timeout > 0:
                await asyncio.wait_for(job.handle(), timeout=float(timeout))
            else:
                await job.handle()
            self._jobs_processed += 1
            await self._dispatch_chain_successor(envelope)
        except asyncio.CancelledError:
            # External cancellation (graceful shutdown) — propagate, never treat
            # as a job failure. A job timeout surfaces as TimeoutError, not this.
            raise
        except Exception as exc:
            if isinstance(exc, TimeoutError):
                logger.warning(
                    "queue.job.timeout",
                    job_class=envelope.job_class,
                    timeout_seconds=timeout,
                )
            envelope.attempts += 1
            retry_until = getattr(job, "retry_until", None)
            retry_until_expired = retry_until is not None and datetime.now(UTC) > retry_until
            if envelope.attempts < job.tries and not retry_until_expired:
                backoff_delay = job.backoff_for(envelope.attempts)
                envelope.delay = backoff_delay
                await conn.push(envelope, queue=self._queue)
                self._jobs_retried += 1
            else:
                self._jobs_dead += 1
                store = self._failed_job_store
                if store is not None:
                    error_text = "".join(
                        traceback.format_exception(type(exc), exc, exc.__traceback__)
                    )
                    from arvel.queue.failed_job_store import FailedJobStore

                    if isinstance(store, FailedJobStore):
                        await store.create(
                            envelope=envelope,
                            queue=self._queue,
                            error=error_text,
                        )

    async def _dispatch_chain_successor(self, envelope: JobEnvelope) -> None:
        """Pop the next chain step (if any) and enqueue it on its target queue."""
        if not envelope.chain:
            return
        next_step = envelope.chain[0]
        successor = JobEnvelope(
            job_class=next_step.job_class,
            payload=next_step.payload,
            delay=next_step.delay,
            priority=next_step.priority,
            chain=envelope.chain[1:],
        )
        conn = self._manager.connection()
        await conn.push(successor, queue=next_step.queue)


__all__ = ["Worker"]
