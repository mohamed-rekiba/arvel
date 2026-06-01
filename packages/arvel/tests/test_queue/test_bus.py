"""Tests for Bus class and Bus facade"""

from __future__ import annotations

from typing import ClassVar

import pytest
from arvel.facades.bus import Bus as BusFacade
from arvel.queue.bus import Bus
from arvel.queue.config import QueueConfig, QueueDriver
from arvel.queue.job import Job
from arvel.queue.manager import QueueManager


class _BusJob(Job):
    message: str
    executed: ClassVar[list[str]] = []

    async def handle(self) -> None:
        _BusJob.executed.append(self.message)


class _FailBusJob(Job):
    async def handle(self) -> None:
        raise RuntimeError("intentional failure")


def _make_bus() -> tuple[Bus, QueueManager]:
    manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
    return Bus(manager), manager


class TestBusDispatch:
    """Bus.dispatch(job) routes to the configured connection."""

    def setup_method(self) -> None:
        _BusJob.executed.clear()

    @pytest.mark.asyncio
    async def test_dispatch_simple_job(self) -> None:
        bus, _ = _make_bus()
        job = _BusJob(message="dispatched")
        await bus.dispatch(job)
        assert "dispatched" in _BusJob.executed

    @pytest.mark.asyncio
    async def test_dispatch_uses_job_queue(self) -> None:
        bus, _ = _make_bus()
        job = _BusJob(message="high-priority", queue="high")
        await bus.dispatch(job)
        assert "high-priority" in _BusJob.executed


class TestBusBatch:
    """Bus.batch([jobs]) groups jobs together."""

    def setup_method(self) -> None:
        _BusJob.executed.clear()

    @pytest.mark.asyncio
    async def test_batch_dispatches_all_jobs(self) -> None:
        bus, _ = _make_bus()
        jobs = [_BusJob(message=f"batch-{i}") for i in range(3)]
        await bus.batch(jobs)
        for i in range(3):
            assert f"batch-{i}" in _BusJob.executed


class TestBusChain:
    """Bus.chain([jobs]) runs jobs sequentially."""

    def setup_method(self) -> None:
        _BusJob.executed.clear()

    @pytest.mark.asyncio
    async def test_chain_dispatches_all_in_order(self) -> None:
        bus, _ = _make_bus()
        jobs = [_BusJob(message=f"chain-{i}") for i in range(3)]
        await bus.chain(jobs)
        executed = [m for m in _BusJob.executed if m.startswith("chain-")]
        assert executed == ["chain-0", "chain-1", "chain-2"]

    @pytest.mark.asyncio
    async def test_chain_stops_on_failure(self) -> None:
        """A failing job in a chain prevents subsequent jobs from running."""
        bus, _ = _make_bus()
        jobs: list[Job] = [_FailBusJob(), _BusJob(message="after-failure")]
        with pytest.raises(RuntimeError):
            await bus.chain(jobs)
        assert "after-failure" not in _BusJob.executed


class TestBusFacade:
    """Bus facade proxies to Bus instance."""

    def test_facade_not_bound_raises(self) -> None:
        from arvel.queue.exceptions import FacadeNotBoundError

        BusFacade.manager = None
        with pytest.raises(FacadeNotBoundError):
            BusFacade.mgr()

    def test_facade_bind_connects_manager(self) -> None:
        from arvel.container import Container

        container = Container()
        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        container.instance(QueueManager, manager)
        BusFacade.bind(container)
        assert BusFacade.manager is not None
        assert BusFacade.mgr() is manager

    @pytest.mark.asyncio
    async def test_facade_dispatch_proxies_to_manager(self) -> None:
        _BusJob.executed.clear()
        _, manager = _make_bus()
        BusFacade.manager = manager

        await BusFacade.dispatch(_BusJob(message="via-facade"))

        assert _BusJob.executed == ["via-facade"]

    @pytest.mark.asyncio
    async def test_facade_batch_proxies_to_manager(self) -> None:
        _BusJob.executed.clear()
        _, manager = _make_bus()
        BusFacade.manager = manager

        await BusFacade.batch([_BusJob(message=f"facade-batch-{idx}") for idx in range(3)])

        assert _BusJob.executed == [
            "facade-batch-0",
            "facade-batch-1",
            "facade-batch-2",
        ]

    @pytest.mark.asyncio
    async def test_facade_chain_proxies_to_manager(self) -> None:
        _BusJob.executed.clear()
        _, manager = _make_bus()
        BusFacade.manager = manager

        await BusFacade.chain([_BusJob(message=f"facade-chain-{idx}") for idx in range(3)])

        assert _BusJob.executed == [
            "facade-chain-0",
            "facade-chain-1",
            "facade-chain-2",
        ]
