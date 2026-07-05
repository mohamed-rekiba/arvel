"""Queues (doc 12) — worker retry/backoff + failed() enforcement. Test-first."""

from __future__ import annotations

from arvel.queue import Job, run_job_with_retries


class FlakyForever(Job):
    tries = 3
    backoff = 0

    def __init__(self) -> None:
        self.attempts = 0
        self.failed_with: BaseException | None = None

    async def handle(self) -> None:
        self.attempts += 1
        raise ValueError("boom")

    async def failed(self, exc: BaseException) -> None:
        self.failed_with = exc


class RecoversOnSecond(Job):
    tries = 3
    backoff = 0

    def __init__(self) -> None:
        self.attempts = 0

    async def handle(self) -> str:
        self.attempts += 1
        if self.attempts < 2:
            raise ValueError("transient")
        return "ok"


class BackoffList(Job):
    tries = 3
    backoff = (10, 30)  # per-attempt delays

    async def handle(self) -> None:
        raise ValueError("always")

    async def failed(self, exc: BaseException) -> None: ...


async def _no_sleep(_delay: float, _store: list[float]) -> None:
    _store.append(_delay)


async def test_exhausts_tries_then_calls_failed() -> None:
    job = FlakyForever()
    slept: list[float] = []
    await run_job_with_retries(job, sleep=lambda d: _no_sleep(d, slept))
    assert job.attempts == 3  # tried the full `tries`
    assert isinstance(job.failed_with, ValueError)  # failed() got the last exception


async def test_succeeds_on_retry_without_failing() -> None:
    job = RecoversOnSecond()
    slept: list[float] = []
    result = await run_job_with_retries(job, sleep=lambda d: _no_sleep(d, slept))
    assert result == "ok"
    assert job.attempts == 2


async def test_backoff_list_delays_between_attempts() -> None:
    job = BackoffList()
    slept: list[float] = []
    await run_job_with_retries(job, sleep=lambda d: _no_sleep(d, slept))
    assert slept == [10, 30]  # waited backoff[0], then backoff[1] (2 gaps for 3 attempts)


class MaxExceptionsCapped(Job):
    tries = 10
    backoff = 0
    max_exceptions = 2  # a lower ceiling than `tries` — should win

    def __init__(self) -> None:
        self.attempts = 0

    async def handle(self) -> None:
        self.attempts += 1
        raise ValueError("boom")

    async def failed(self, exc: BaseException) -> None: ...


async def test_max_exceptions_caps_attempts_below_tries() -> None:
    job = MaxExceptionsCapped()
    slept: list[float] = []
    await run_job_with_retries(job, sleep=lambda d: _no_sleep(d, slept))
    assert job.attempts == 2  # capped by max_exceptions, well under tries=10


class RetryUntilAlreadyPast(Job):
    tries = 10
    backoff = 0

    def __init__(self) -> None:
        from datetime import UTC, datetime, timedelta

        self.attempts = 0
        self.retry_until = datetime.now(UTC) - timedelta(seconds=1)

    async def handle(self) -> None:
        self.attempts += 1
        raise ValueError("boom")

    async def failed(self, exc: BaseException) -> None: ...


async def test_retry_until_in_the_past_stops_after_one_attempt() -> None:
    job = RetryUntilAlreadyPast()
    slept: list[float] = []
    await run_job_with_retries(job, sleep=lambda d: _no_sleep(d, slept))
    assert job.attempts == 1  # `tries=10` never mattered — retry_until already passed
