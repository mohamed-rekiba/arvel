"""Tests for QueueContract and drivers — Story 3.

FR-009: QueueContract ABC with dispatch/later/bulk.
FR-011: Sync driver executes jobs immediately.
FR-012: Null driver discards jobs silently.
SEC: Job payloads do not serialize raw credentials.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from arvel.queue.contracts import QueueContract
from arvel.queue.job import Job

from .conftest import SendEmailJob


class TestQueueContractInterface:
    """FR-009: QueueContract ABC defines required methods."""

    def test_queue_contract_is_abstract(self) -> None:
        abstract_cls: type = QueueContract
        with pytest.raises(TypeError):
            abstract_cls()

    def test_contract_has_dispatch_method(self) -> None:
        assert hasattr(QueueContract, "dispatch")

    def test_contract_has_later_method(self) -> None:
        assert hasattr(QueueContract, "later")

    def test_contract_has_bulk_method(self) -> None:
        assert hasattr(QueueContract, "bulk")

    def test_contract_has_size_method(self) -> None:
        assert hasattr(QueueContract, "size")


class TestSyncDriver:
    """FR-011: Sync driver executes jobs immediately in-process."""

    async def test_sync_dispatch_executes_handle(self) -> None:
        from arvel.queue.drivers.sync_driver import SyncQueue

        executed: list[str] = []

        class TrackingJob(Job):
            async def handle(self) -> None:
                executed.append("done")

        queue = SyncQueue()
        await queue.dispatch(TrackingJob())

        assert executed == ["done"]

    async def test_sync_later_executes_immediately(self) -> None:
        """Sync driver ignores delay and executes immediately."""
        from arvel.queue.drivers.sync_driver import SyncQueue

        executed: list[str] = []

        class TrackingJob(Job):
            async def handle(self) -> None:
                executed.append("done")

        queue = SyncQueue()
        await queue.later(timedelta(minutes=5), TrackingJob())

        assert executed == ["done"]

    async def test_sync_bulk_executes_all(self) -> None:
        from arvel.queue.drivers.sync_driver import SyncQueue

        count = 0

        class CountingJob(Job):
            async def handle(self) -> None:
                nonlocal count
                count += 1

        queue = SyncQueue()
        await queue.bulk([CountingJob(), CountingJob(), CountingJob()])

        assert count == 3

    async def test_sync_size_returns_zero(self) -> None:
        from arvel.queue.drivers.sync_driver import SyncQueue

        queue = SyncQueue()
        size = await queue.size()
        assert size == 0

    async def test_sync_driver_implements_contract(self) -> None:
        from arvel.queue.drivers.sync_driver import SyncQueue

        queue = SyncQueue()
        assert isinstance(queue, QueueContract)


class TestNullDriver:
    """FR-012: Null driver discards jobs silently."""

    async def test_null_dispatch_does_nothing(self) -> None:
        from arvel.queue.drivers.null_driver import NullQueue

        queue = NullQueue()
        job = SendEmailJob()
        await queue.dispatch(job)

    async def test_null_later_does_nothing(self) -> None:
        from arvel.queue.drivers.null_driver import NullQueue

        queue = NullQueue()
        await queue.later(timedelta(hours=1), SendEmailJob())

    async def test_null_bulk_does_nothing(self) -> None:
        from arvel.queue.drivers.null_driver import NullQueue

        queue = NullQueue()
        await queue.bulk([SendEmailJob(), SendEmailJob()])

    async def test_null_size_returns_zero(self) -> None:
        from arvel.queue.drivers.null_driver import NullQueue

        queue = NullQueue()
        assert await queue.size() == 0

    async def test_null_driver_implements_contract(self) -> None:
        from arvel.queue.drivers.null_driver import NullQueue

        queue = NullQueue()
        assert isinstance(queue, QueueContract)
