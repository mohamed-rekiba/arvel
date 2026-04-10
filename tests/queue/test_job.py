"""Tests for Job base class — Story 4.

FR-013: Job base class with handle().
FR-014: Configurable retry count and backoff.
FR-015: Job timeout.
FR-016: Per-job middleware.
FR-017: Failed job recording.
FR-018: DI-resolved dependencies in handle().
FR-019: Job on_failure() callback.
NFR-007: Failed job payloads redact sensitive fields.
"""

from __future__ import annotations

import pytest

from arvel.queue.job import Job

from .conftest import (
    FailingJob,
    JobWithCallback,
    JobWithMiddleware,
    SendEmailJob,
    SlowJob,
)


class TestJobBaseClass:
    """FR-013: Job base class with handle() method."""

    def test_job_has_handle_method(self) -> None:
        assert hasattr(Job, "handle")

    def test_job_is_pydantic_model(self) -> None:
        job = SendEmailJob()
        data = job.model_dump()
        assert "to" in data
        assert "subject" in data

    def test_job_serializes_to_json(self) -> None:
        job = SendEmailJob(to="x@y.com", subject="Test")
        json_str = job.model_dump_json()
        assert "x@y.com" in json_str

    def test_job_deserializes_from_dict(self) -> None:
        job = SendEmailJob.model_validate({"to": "a@b.com", "subject": "Hi"})
        assert job.to == "a@b.com"

    async def test_handle_raises_not_implemented_on_base(self) -> None:
        with pytest.raises(NotImplementedError):
            await Job().handle()


class TestJobRetryConfig:
    """FR-014: Configurable retry count and backoff."""

    def test_default_max_retries(self) -> None:
        job = SendEmailJob()
        assert job.max_retries == 3

    def test_default_backoff(self) -> None:
        job = SendEmailJob()
        assert job.backoff == 60

    def test_custom_retries(self) -> None:
        job = FailingJob()
        assert job.max_retries == 2
        assert job.backoff == 1

    def test_retry_config_serializable(self) -> None:
        job = FailingJob()
        data = job.model_dump()
        assert data["max_retries"] == 2


class TestJobTimeout:
    """FR-015: Job timeout."""

    def test_default_timeout(self) -> None:
        job = SendEmailJob()
        assert job.timeout_seconds == 300

    def test_custom_timeout(self) -> None:
        job = SlowJob()
        assert job.timeout_seconds == 1


class TestJobMiddleware:
    """FR-016: Per-job middleware via middleware() method."""

    def test_middleware_returns_list(self) -> None:
        job = JobWithMiddleware()
        assert isinstance(job.middleware(), list)

    def test_default_middleware_is_empty(self) -> None:
        job = SendEmailJob()
        assert job.middleware() == []


class TestJobOnFailure:
    """FR-019: Job on_failure() callback."""

    async def test_on_failure_exists(self) -> None:
        job = JobWithCallback()
        assert hasattr(job, "on_failure")

    async def test_on_failure_callable(self) -> None:
        job = JobWithCallback()
        await job.on_failure(RuntimeError("test"))


class TestJobQueueName:
    """Jobs can specify which queue they run on."""

    def test_default_queue_name(self) -> None:
        job = SendEmailJob()
        assert job.queue_name == "default"

    def test_custom_queue_name(self) -> None:
        class HighPriorityJob(Job):
            queue_name: str = "high"

            async def handle(self) -> None:
                pass

        job = HighPriorityJob()
        assert job.queue_name == "high"
