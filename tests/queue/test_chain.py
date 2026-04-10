"""Tests for Job Chaining — Story 5.

FR-020: Chain dispatches jobs sequentially.
FR-021: Chain halts on permanent failure.
"""

from __future__ import annotations

import pytest

from .conftest import ChainStepA, ChainStepB, ChainStepC


class TestChainSequential:
    """FR-020: Chain dispatches jobs in sequence."""

    async def test_chain_dispatches_in_order(self) -> None:
        from arvel.queue.chain import Chain

        chain = Chain(ChainStepA(), ChainStepB(), ChainStepC())
        assert isinstance(chain.jobs[0], ChainStepA)
        assert chain.jobs[0].step == "A"
        assert isinstance(chain.jobs[1], ChainStepB)
        assert chain.jobs[1].step == "B"
        assert isinstance(chain.jobs[2], ChainStepC)
        assert chain.jobs[2].step == "C"

    async def test_chain_dispatch_executes_all(self) -> None:
        from arvel.queue.chain import Chain
        from arvel.queue.drivers.sync_driver import SyncQueue

        executed: list[str] = []

        from arvel.queue.job import Job

        class TrackA(Job):
            async def handle(self) -> None:
                executed.append("A")

        class TrackB(Job):
            async def handle(self) -> None:
                executed.append("B")

        class TrackC(Job):
            async def handle(self) -> None:
                executed.append("C")

        chain = Chain(TrackA(), TrackB(), TrackC())
        queue = SyncQueue()
        await chain.dispatch(queue)

        assert executed == ["A", "B", "C"]

    async def test_chain_with_single_job(self) -> None:
        from arvel.queue.chain import Chain

        chain = Chain(ChainStepA())
        assert len(chain.jobs) == 1


class TestChainFailure:
    """FR-021: Chain halts on permanent failure."""

    async def test_chain_halts_on_failure(self) -> None:
        from arvel.queue.chain import Chain
        from arvel.queue.drivers.sync_driver import SyncQueue

        executed: list[str] = []

        from arvel.queue.job import Job

        class TrackA(Job):
            async def handle(self) -> None:
                executed.append("A")

        class TrackFail(Job):
            max_retries: int = 0

            async def handle(self) -> None:
                raise RuntimeError("fail")

        class TrackC(Job):
            async def handle(self) -> None:
                executed.append("C")

        chain = Chain(TrackA(), TrackFail(), TrackC())
        queue = SyncQueue()

        from arvel.queue.exceptions import JobMaxRetriesError

        with pytest.raises(JobMaxRetriesError):
            await chain.dispatch(queue)

        assert "A" in executed
        assert "C" not in executed
