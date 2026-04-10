"""Tests for JobRunner — Story 1 (Retry/Backoff) + FR-006 (Context Propagation).

AC-001: max_retries honored (3 retries before permanent failure)
AC-002: list backoff [10, 30, 60] per-attempt delays
AC-003: exponential backoff with backoff_base
AC-004: max_exceptions stops retries early
AC-005: retry_until deadline stops retries after elapsed time
AC-006: permanently failed job recorded in FailedJob table
AC-007: on_failure called before recording
AC-008: timeout_seconds enforced
AC-009: timed-out job counts as failed attempt
AC-023: context dehydrated on dispatch
AC-024: context hydrated before handle
AC-025: context flushed after execution
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from arvel.context.context_store import Context
from arvel.queue.exceptions import JobMaxRetriesError
from arvel.queue.job import Job
from arvel.queue.worker import JobRunner


class CountingJob(Job):
    max_retries: int = 3
    backoff: int | list[int] | str = 0
    call_count: int = 0
    fail_times: int = 999

    async def handle(self) -> None:
        self.call_count += 1
        if self.call_count <= self.fail_times:
            raise RuntimeError(f"fail #{self.call_count}")


class SucceedingJob(Job):
    handled: bool = False

    async def handle(self) -> None:
        self.handled = True


class OnFailureTracker(Job):
    max_retries: int = 1
    backoff: int | list[int] | str = 0
    failure_error: str = ""

    async def handle(self) -> None:
        raise RuntimeError("always fails")

    async def on_failure(self, error: Exception) -> None:
        self.failure_error = str(error)


class TimeoutJob(Job):
    timeout_seconds: int = 1
    max_retries: int = 0
    backoff: int | list[int] | str = 0

    async def handle(self) -> None:
        import anyio

        await anyio.sleep(10)


class MaxExceptionsJob(Job):
    max_retries: int = 10
    max_exceptions: int = 2
    backoff: int | list[int] | str = 0
    call_count: int = 0

    async def handle(self) -> None:
        self.call_count += 1
        raise RuntimeError("always fails")


class ContextAwareJob(Job):
    captured_request_id: str = ""

    async def handle(self) -> None:
        self.captured_request_id = Context.get("request_id", "")


# ──── AC-001: max_retries honored ────


class TestRetryBasic:
    async def test_job_retried_up_to_max_retries(self) -> None:
        job = CountingJob(max_retries=3, fail_times=999)
        runner = JobRunner()
        with pytest.raises(JobMaxRetriesError):
            await runner.execute(job)
        assert job.call_count == 4  # 1 initial + 3 retries

    async def test_job_succeeds_on_retry(self) -> None:
        job = CountingJob(max_retries=3, fail_times=2, backoff=0)
        runner = JobRunner()
        await runner.execute(job)
        assert job.call_count == 3  # fails twice, succeeds on third

    async def test_zero_retries_fails_immediately(self) -> None:
        job = CountingJob(max_retries=0, fail_times=999)
        runner = JobRunner()
        with pytest.raises(JobMaxRetriesError):
            await runner.execute(job)
        assert job.call_count == 1


# ──── AC-002: list backoff ────


class TestListBackoff:
    async def test_list_backoff_computes_correct_delays(self) -> None:
        runner = JobRunner()
        job = CountingJob(max_retries=3, backoff=[10, 30, 60])
        delays = runner._compute_backoff_delays(job)
        assert delays == [10, 30, 60]

    async def test_list_backoff_repeats_last_for_overflow(self) -> None:
        runner = JobRunner()
        job = CountingJob(max_retries=5, backoff=[10, 30])
        delays = runner._compute_backoff_delays(job)
        assert delays == [10, 30, 30, 30, 30]


# ──── AC-003: exponential backoff ────


class TestExponentialBackoff:
    async def test_exponential_backoff_with_base_2(self) -> None:
        runner = JobRunner()
        job = CountingJob(max_retries=4, backoff="exponential", backoff_base=2)
        delays = runner._compute_backoff_delays(job)
        assert delays == [2, 4, 8, 16]

    async def test_exponential_backoff_with_base_3(self) -> None:
        runner = JobRunner()
        job = CountingJob(max_retries=3, backoff="exponential", backoff_base=3)
        delays = runner._compute_backoff_delays(job)
        assert delays == [3, 9, 27]


# ──── AC-004: max_exceptions ────


class TestMaxExceptions:
    async def test_max_exceptions_stops_retries_early(self) -> None:
        job = MaxExceptionsJob()
        runner = JobRunner()
        with pytest.raises(JobMaxRetriesError):
            await runner.execute(job)
        assert job.call_count == 2  # max_exceptions=2, stops after 2


# ──── AC-005: retry_until ────


class TestRetryUntil:
    async def test_retry_until_stops_after_deadline(self) -> None:
        job = CountingJob(
            max_retries=100,
            backoff=0,
            fail_times=999,
            retry_until=timedelta(seconds=0),
        )
        runner = JobRunner()
        with pytest.raises(JobMaxRetriesError):
            await runner.execute(job)
        assert job.call_count == 1  # deadline already passed


# ──── AC-007: on_failure called ────


class TestOnFailure:
    async def test_on_failure_called_on_permanent_failure(self) -> None:
        job = OnFailureTracker()
        runner = JobRunner()
        with pytest.raises(JobMaxRetriesError):
            await runner.execute(job)
        assert job.failure_error == "always fails"


# ──── AC-008 / AC-009: timeout ────


class TestTimeout:
    async def test_timeout_raises_on_slow_job(self) -> None:
        job = TimeoutJob()
        runner = JobRunner()
        with pytest.raises(JobMaxRetriesError):
            await runner.execute(job)

    async def test_timeout_counts_as_failed_attempt(self) -> None:
        class RetryingTimeoutJob(Job):
            timeout_seconds: int = 1
            max_retries: int = 1
            backoff: int | list[int] | str = 0
            call_count: int = 0

            async def handle(self) -> None:
                self.call_count += 1
                if self.call_count == 1:
                    import anyio

                    await anyio.sleep(10)

        job = RetryingTimeoutJob()
        runner = JobRunner()
        await runner.execute(job)
        assert job.call_count == 2  # first timed out, second succeeded


# ──── AC-023/024/025: context propagation ────


class TestContextPropagation:
    async def test_context_hydrated_before_handle(self) -> None:
        Context.flush()
        Context.add("request_id", "req-123")
        context_data = Context.dehydrate()
        Context.flush()

        job = ContextAwareJob()
        runner = JobRunner()
        await runner.execute(job, context=context_data)
        assert job.captured_request_id == "req-123"

    async def test_context_flushed_after_execution(self) -> None:
        Context.flush()
        context_data = {"request_id": "req-456"}

        job = SucceedingJob()
        runner = JobRunner()
        await runner.execute(job, context=context_data)
        assert Context.get("request_id") is None

    async def test_execute_without_context_works(self) -> None:
        job = SucceedingJob()
        runner = JobRunner()
        await runner.execute(job)
        assert job.handled is True
