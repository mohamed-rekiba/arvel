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


class TestBusDispatchMany:
    """Bus.dispatch_many([jobs]) fans out jobs independently."""

    def setup_method(self) -> None:
        _BusJob.executed.clear()

    @pytest.mark.asyncio
    async def test_dispatch_many_dispatches_all_jobs(self) -> None:
        bus, _ = _make_bus()
        jobs = [_BusJob(message=f"fanout-{i}") for i in range(3)]
        await bus.dispatch_many(jobs)
        for i in range(3):
            assert f"fanout-{i}" in _BusJob.executed


class TestBusChain:
    """Bus.chain([jobs]) runs jobs sequentially, stopping on failure."""

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
        # SYNC driver: head failure halts the chain at the boundary, so
        # successors that travel on its envelope never get pushed.
        bus, _ = _make_bus()
        jobs: list[Job] = [_FailBusJob(), _BusJob(message="after-failure")]
        with pytest.raises(RuntimeError):
            await bus.chain(jobs)
        assert "after-failure" not in _BusJob.executed

    @pytest.mark.asyncio
    async def test_chain_carries_tail_on_head_envelope(self) -> None:
        # Real chain semantics: only the head is pushed; successors travel
        # along on envelope.chain and are dispatched by the worker / sync
        # driver after handle() returns cleanly.
        from arvel.queue.config import QueueConfig, QueueDriver
        from arvel.queue.envelope import JobEnvelope
        from arvel.queue.manager import QueueManager

        captured: list[JobEnvelope] = []

        # Stub satisfies the slice of QueueConnection the test exercises.
        # Bus.chain only calls push().
        class _RecordingSync:
            async def push(self, envelope: JobEnvelope, queue: str = "default") -> None:
                captured.append(envelope)

        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        manager._connections[QueueDriver.SYNC] = _RecordingSync()  # type: ignore[assignment]
        bus = Bus(manager)
        jobs: list[Job] = [_BusJob(message=f"link-{i}") for i in range(3)]
        await bus.chain(jobs)
        assert len(captured) == 1, "only the head should be pushed at chain time"
        head = captured[0]
        assert [step.payload["message"] for step in head.chain] == ["link-1", "link-2"]


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
    async def test_facade_dispatch_many_proxies_to_manager(self) -> None:
        _BusJob.executed.clear()
        _, manager = _make_bus()
        BusFacade.manager = manager

        await BusFacade.dispatch_many([_BusJob(message=f"facade-fanout-{idx}") for idx in range(3)])

        assert _BusJob.executed == [
            "facade-fanout-0",
            "facade-fanout-1",
            "facade-fanout-2",
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


class _OtherJob(Job):
    tag: str

    async def handle(self) -> None:
        return None


class TestBusFake:
    """Bus.fake() records dispatches; nothing executes."""

    def setup_method(self) -> None:
        _BusJob.executed.clear()
        _, manager = _make_bus()
        BusFacade.manager = manager

    @pytest.mark.asyncio
    async def test_fake_records_dispatches_without_executing(self) -> None:
        with BusFacade.fake() as ctx:
            await BusFacade.dispatch(_BusJob(message="captured"))
            assert _BusJob.executed == []
            assert len(ctx.fake.pushed) == 1
            assert ctx.fake.pushed[0].envelope.payload["message"] == "captured"

    @pytest.mark.asyncio
    async def test_assert_dispatched_passes_and_fails(self) -> None:
        with BusFacade.fake():
            await BusFacade.dispatch(_BusJob(message="x"))
            BusFacade.assert_dispatched(_BusJob)
            BusFacade.assert_dispatched(_BusJob, times=1)

            with pytest.raises(AssertionError, match="not dispatched"):
                BusFacade.assert_dispatched(_OtherJob)
            with pytest.raises(AssertionError, match="expected 2 dispatches"):
                BusFacade.assert_dispatched(_BusJob, times=2)

    @pytest.mark.asyncio
    async def test_assert_not_dispatched(self) -> None:
        with BusFacade.fake():
            BusFacade.assert_not_dispatched(_BusJob)
            await BusFacade.dispatch(_BusJob(message="x"))
            with pytest.raises(AssertionError, match="dispatched 1 time"):
                BusFacade.assert_not_dispatched(_BusJob)

    @pytest.mark.asyncio
    async def test_assert_dispatched_on_queue(self) -> None:
        with BusFacade.fake():
            await BusFacade.dispatch(_BusJob(message="x", queue="high"))
            BusFacade.assert_dispatched_on(_BusJob, "high")
            with pytest.raises(AssertionError, match="was not dispatched on queue 'low'"):
                BusFacade.assert_dispatched_on(_BusJob, "low")

    @pytest.mark.asyncio
    async def test_assert_chained(self) -> None:
        with BusFacade.fake():
            await BusFacade.chain(
                [
                    _BusJob(message="head"),
                    _BusJob(message="mid"),
                    _OtherJob(tag="tail"),
                ]
            )
            BusFacade.assert_chained(_BusJob, _BusJob, _OtherJob)
            with pytest.raises(AssertionError, match="No dispatched"):
                BusFacade.assert_chained(_BusJob, _OtherJob, _BusJob)

    @pytest.mark.asyncio
    async def test_assert_chained_when_head_missing(self) -> None:
        with BusFacade.fake(), pytest.raises(AssertionError, match="was not dispatched"):
            BusFacade.assert_chained(_BusJob, _OtherJob)

    def test_asserts_require_fake_context(self) -> None:
        with pytest.raises(TypeError, match="requires Bus.fake"):
            BusFacade.assert_dispatched(_BusJob)
        with pytest.raises(TypeError, match="requires Bus.fake"):
            BusFacade.assert_not_dispatched(_BusJob)
        with pytest.raises(TypeError, match="requires Bus.fake"):
            BusFacade.assert_dispatched_on(_BusJob, "default")
        with pytest.raises(TypeError, match="requires Bus.fake"):
            BusFacade.assert_chained(_BusJob, _OtherJob)

    @pytest.mark.asyncio
    async def test_fake_restores_previous_connection_on_exit(self) -> None:
        # Force-create the real connection so we can check it's restored.
        mgr = BusFacade.mgr()
        original = mgr.connection()
        with BusFacade.fake():
            assert mgr.connection() is not original
        assert mgr.connection() is original
