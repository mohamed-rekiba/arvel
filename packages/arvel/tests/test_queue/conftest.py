"""Queue test suite — shared fixtures."""

from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest
import pytest_asyncio
from arvel.queue.config import QueueConfig, QueueDriver
from arvel.queue.job import Job
from arvel.queue.manager import QueueManager


class SimpleJob(Job):
    message: str
    executed: ClassVar[list[str]] = []

    async def handle(self) -> None:
        SimpleJob.executed.append(self.message)


class FailingJob(Job):
    async def handle(self) -> None:
        raise RuntimeError("intentional failure")


class SlowJob(Job):
    sleep_seconds: float = 0.05

    async def handle(self) -> None:
        await asyncio.sleep(self.sleep_seconds)


@pytest.fixture(autouse=True)
def clear_job_state() -> None:
    SimpleJob.executed.clear()


@pytest.fixture
def simple_job() -> SimpleJob:
    return SimpleJob(message="hello")


@pytest.fixture
def failing_job() -> FailingJob:
    return FailingJob()


@pytest_asyncio.fixture
async def sync_manager() -> QueueManager:
    config = QueueConfig(connection=QueueDriver.SYNC)
    return QueueManager(config)
