"""Tests for TaskiqQueue — contract compliance (InMemoryBroker), import guard, broker factory."""

from __future__ import annotations

from datetime import timedelta
from importlib import util
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arvel.queue.contracts import QueueContract
from arvel.queue.exceptions import QueueError
from arvel.queue.job import Job

_has_taskiq = util.find_spec("taskiq") is not None
_requires_taskiq = pytest.mark.skipif(not _has_taskiq, reason="taskiq not installed")


class _TrackingJob(Job):
    to: str = "user@example.com"

    async def handle(self) -> None:
        pass


class TestTaskiqImportGuard:
    """TaskiqQueue raises a clear error when taskiq is not installed."""

    def test_import_guard_raises_queue_error(self) -> None:
        with patch.dict("sys.modules", {"taskiq": None}):
            from arvel.queue.drivers.taskiq_driver import _require_taskiq

            with pytest.raises(QueueError, match="taskiq is not installed"):
                _require_taskiq()


class TestTaskiqQueueContract:
    """TaskiqQueue implements QueueContract."""

    def test_taskiq_queue_is_queue_contract(self) -> None:
        from arvel.queue.drivers.taskiq_driver import TaskiqQueue

        mock_broker = MagicMock()
        queue = TaskiqQueue(broker=mock_broker)
        assert isinstance(queue, QueueContract)


class TestTaskiqBrokerFactory:
    """create_broker builds the correct broker by type."""

    @_requires_taskiq
    def test_create_memory_broker(self) -> None:
        from taskiq import InMemoryBroker

        from arvel.queue.drivers.taskiq_driver import create_broker

        broker = create_broker("memory")
        assert isinstance(broker, InMemoryBroker)

    @_requires_taskiq
    def test_create_redis_broker(self) -> None:
        taskiq_redis = pytest.importorskip("taskiq_redis", reason="taskiq-redis not installed")

        from arvel.queue.drivers.taskiq_driver import create_broker

        broker = create_broker("redis", "redis://localhost:6379")
        assert isinstance(broker, taskiq_redis.ListQueueBroker)

    def test_unknown_broker_type_raises(self) -> None:
        from arvel.queue.drivers.taskiq_driver import create_broker

        with pytest.raises(QueueError, match="Unknown Taskiq broker type"):
            create_broker("kafka")

    def test_nats_broker_missing_raises(self) -> None:
        from arvel.queue.drivers.taskiq_driver import create_broker

        with (
            patch.dict("sys.modules", {"taskiq_nats": None}),
            pytest.raises(QueueError, match="taskiq-nats is not installed"),
        ):
            create_broker("nats")

    def test_rabbitmq_broker_missing_raises(self) -> None:
        from arvel.queue.drivers.taskiq_driver import create_broker

        with (
            patch.dict("sys.modules", {"taskiq_aio_pika": None}),
            pytest.raises(QueueError, match="taskiq-aio-pika is not installed"),
        ):
            create_broker("rabbitmq")


@_requires_taskiq
class TestTaskiqQueueDispatch:
    """TaskiqQueue.dispatch registers a task and calls kiq."""

    async def test_dispatch_registers_and_kicks(self) -> None:
        from arvel.queue.drivers.taskiq_driver import TaskiqQueue

        mock_task = MagicMock()
        mock_task.kiq = AsyncMock()
        mock_broker = MagicMock()
        mock_broker.register_task = MagicMock(return_value=mock_task)

        queue = TaskiqQueue(broker=mock_broker)
        job = _TrackingJob()
        await queue.dispatch(job)

        mock_broker.register_task.assert_called_once()
        mock_task.kiq.assert_awaited_once()

    async def test_dispatch_passes_job_data(self) -> None:
        from arvel.queue.drivers.taskiq_driver import TaskiqQueue

        mock_task = MagicMock()
        mock_task.kiq = AsyncMock()
        mock_broker = MagicMock()
        mock_broker.register_task = MagicMock(return_value=mock_task)

        queue = TaskiqQueue(broker=mock_broker)
        job = _TrackingJob(to="specific@example.com")
        await queue.dispatch(job)

        call_kwargs = mock_task.kiq.call_args[1]
        assert "specific@example.com" in str(call_kwargs["job_data"])


@_requires_taskiq
class TestTaskiqQueueLater:
    """TaskiqQueue.later dispatches with delay labels."""

    async def test_later_passes_delay_label(self) -> None:
        from arvel.queue.drivers.taskiq_driver import TaskiqQueue

        mock_task = MagicMock()
        mock_task.kiq = AsyncMock()
        mock_broker = MagicMock()
        mock_broker.register_task = MagicMock(return_value=mock_task)

        queue = TaskiqQueue(broker=mock_broker)
        delay = timedelta(minutes=5)
        await queue.later(delay, _TrackingJob())

        call_kwargs = mock_task.kiq.call_args[1]
        assert call_kwargs["labels"]["delay"] == 300


@_requires_taskiq
class TestTaskiqQueueBulk:
    """TaskiqQueue.bulk dispatches each job."""

    async def test_bulk_dispatches_all(self) -> None:
        from arvel.queue.drivers.taskiq_driver import TaskiqQueue

        mock_task = MagicMock()
        mock_task.kiq = AsyncMock()
        mock_broker = MagicMock()
        mock_broker.register_task = MagicMock(return_value=mock_task)

        queue = TaskiqQueue(broker=mock_broker)
        jobs = [_TrackingJob(), _TrackingJob(), _TrackingJob()]
        await queue.bulk(jobs)

        assert mock_task.kiq.await_count == 3


class TestTaskiqQueueSize:
    """TaskiqQueue.size returns 0 (Taskiq doesn't expose queue size)."""

    async def test_size_returns_zero(self) -> None:
        from arvel.queue.drivers.taskiq_driver import TaskiqQueue

        mock_broker = MagicMock()
        queue = TaskiqQueue(broker=mock_broker)
        assert await queue.size() == 0


class TestTaskiqQueueClose:
    """TaskiqQueue.close shuts down the broker."""

    async def test_close_calls_shutdown(self) -> None:
        from arvel.queue.drivers.taskiq_driver import TaskiqQueue

        mock_broker = MagicMock()
        mock_broker.shutdown = AsyncMock()

        queue = TaskiqQueue(broker=mock_broker)
        await queue.close()
        mock_broker.shutdown.assert_awaited_once()
