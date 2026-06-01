"""Tests for QueueManager"""

from __future__ import annotations

from typing import ClassVar

import pytest
from arvel.queue.config import QueueConfig, QueueDriver
from arvel.queue.connection import QueueConnection
from arvel.queue.drivers.sync import SyncConnection
from arvel.queue.job import Job
from arvel.queue.manager import QueueManager


class _MgrJob(Job):
    message: str
    executed: ClassVar[list[str]] = []

    async def handle(self) -> None:
        _MgrJob.executed.append(self.message)

    def setup_method(self) -> None:
        _MgrJob.executed.clear()


class TestQueueManagerDriverSelection:
    """QueueManager returns configured driver."""

    def test_default_connection_is_sync(self) -> None:
        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        conn = manager.connection()
        assert isinstance(conn, SyncConnection)

    def test_connection_by_name_sync(self) -> None:
        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        conn = manager.connection("sync")
        assert isinstance(conn, SyncConnection)

    def test_unknown_driver_raises(self) -> None:
        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        with pytest.raises(ValueError, match="unknown_driver"):
            manager.connection("unknown_driver")

    def test_returned_connection_implements_protocol(self) -> None:
        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        conn = manager.connection()
        assert isinstance(conn, QueueConnection)


class TestQueueManagerPassThrough:
    """QueueManager delegates push/pop to active driver."""

    def setup_method(self) -> None:
        _MgrJob.executed.clear()

    @pytest.mark.asyncio
    async def test_push_via_manager(self) -> None:
        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        job = _MgrJob(message="via-manager")
        await manager.push(job)
        assert "via-manager" in _MgrJob.executed

    @pytest.mark.asyncio
    async def test_push_to_named_queue(self) -> None:
        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        job = _MgrJob(message="named-queue")
        await manager.push(job, queue="emails")
        assert "named-queue" in _MgrJob.executed
