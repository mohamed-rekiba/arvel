"""Queues (doc 12) — job timeout enforcement: `Job.timeout` bounds each attempt via
`asyncio.wait_for`; a timeout is treated as a failed attempt (the coroutine is actually cancelled,
cooperatively — never left running), retried/failed per `tries` like any other exception."""

from __future__ import annotations

import asyncio

from arvel.queue import Job, run_job_with_retries


class SlowJob(Job):
    tries = 2
    backoff = 0
    timeout = 0.05

    def __init__(self) -> None:
        self.started = 0
        self.cancelled = False
        self.finished_normally = False

    async def handle(self) -> None:
        self.started += 1
        try:
            await asyncio.sleep(10)
            self.finished_normally = True
        except asyncio.CancelledError:
            self.cancelled = True
            raise


async def _no_sleep(_delay: float) -> None:
    return None


async def test_timeout_cancels_the_job_and_counts_as_a_failed_attempt() -> None:
    job = SlowJob()
    await run_job_with_retries(job, sleep=_no_sleep)
    assert job.started == 2  # both attempts ran (and both timed out)
    assert job.cancelled  # the slow coroutine was actually cancelled, not left running
    assert not job.finished_normally


class QuickJob(Job):
    timeout = 5  # generous — must not interfere with a fast job

    async def handle(self) -> str:
        return "done"


async def test_a_fast_job_is_unaffected_by_its_timeout() -> None:
    job = QuickJob()
    result = await run_job_with_retries(job)
    assert result == "done"
