"""Shared fixtures for the arvel.queue test suite."""

from __future__ import annotations

import pytest

from arvel.queue.job import Job

# ──── Test Jobs ────


class SendEmailJob(Job):
    to: str = "test@example.com"
    subject: str = "Hello"

    async def handle(self) -> None:
        pass


class FailingJob(Job):
    max_retries: int = 2
    backoff: int | list[int] | str = 1

    async def handle(self) -> None:
        raise RuntimeError("intentional failure")


class SlowJob(Job):
    timeout_seconds: int = 1

    async def handle(self) -> None:
        import asyncio

        await asyncio.sleep(10)


class JobWithMiddleware(Job):
    async def handle(self) -> None:
        pass

    def middleware(self) -> list[object]:
        return []


class JobWithCallback(Job):
    async def handle(self) -> None:
        pass

    async def on_failure(self, error: Exception) -> None:
        pass


class ChainStepA(Job):
    step: str = "A"

    async def handle(self) -> None:
        pass


class ChainStepB(Job):
    step: str = "B"

    async def handle(self) -> None:
        pass


class ChainStepC(Job):
    step: str = "C"

    async def handle(self) -> None:
        pass


class ChainStepFailing(Job):
    step: str = "fail"
    max_retries: int = 0

    async def handle(self) -> None:
        raise RuntimeError("chain step failed")


class BatchJob1(Job):
    name: str = "batch_1"

    async def handle(self) -> None:
        pass


class BatchJob2(Job):
    name: str = "batch_2"

    async def handle(self) -> None:
        pass


class BatchJob3(Job):
    name: str = "batch_3"

    async def handle(self) -> None:
        pass


class BatchJobFailing(Job):
    name: str = "batch_fail"
    max_retries: int = 0

    async def handle(self) -> None:
        raise RuntimeError("batch job failed")


class OnBatchComplete(Job):
    async def handle(self) -> None:
        pass


# ──── Fixtures ────


@pytest.fixture
def send_email_job() -> SendEmailJob:
    return SendEmailJob()


@pytest.fixture
def failing_job() -> FailingJob:
    return FailingJob()
