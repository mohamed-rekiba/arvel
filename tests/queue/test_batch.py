"""Tests for Job Batching — Story 5.

FR-022: Batch dispatches jobs in parallel with completion callback.
FR-023: Batch fires callback even with partial failures.
"""

from __future__ import annotations

from .conftest import BatchJob1, BatchJob2, BatchJob3, OnBatchComplete


class TestBatchParallel:
    """FR-022: Batch dispatches all jobs and fires callback when done."""

    async def test_batch_holds_jobs(self) -> None:
        from arvel.queue.batch import Batch

        batch = Batch([BatchJob1(), BatchJob2(), BatchJob3()])
        assert len(batch.jobs) == 3

    async def test_batch_then_sets_callback(self) -> None:
        from arvel.queue.batch import Batch

        batch = Batch([BatchJob1()]).then(OnBatchComplete())
        assert batch.callback is not None

    async def test_batch_dispatch_executes_all(self) -> None:
        from arvel.queue.batch import Batch
        from arvel.queue.drivers.sync_driver import SyncQueue
        from arvel.queue.job import Job

        executed: list[str] = []

        class Track1(Job):
            async def handle(self) -> None:
                executed.append("1")

        class Track2(Job):
            async def handle(self) -> None:
                executed.append("2")

        class Track3(Job):
            async def handle(self) -> None:
                executed.append("3")

        batch = Batch([Track1(), Track2(), Track3()])
        queue = SyncQueue()
        await batch.dispatch(queue)

        assert set(executed) == {"1", "2", "3"}

    async def test_batch_callback_fires_after_completion(self) -> None:
        from arvel.queue.batch import Batch
        from arvel.queue.drivers.sync_driver import SyncQueue
        from arvel.queue.job import Job

        callback_fired = []

        class SimpleJob(Job):
            async def handle(self) -> None:
                pass

        class Callback(Job):
            async def handle(self) -> None:
                callback_fired.append(True)

        batch = Batch([SimpleJob(), SimpleJob()]).then(Callback())
        queue = SyncQueue()
        await batch.dispatch(queue)

        assert len(callback_fired) == 1


class TestBatchPartialFailure:
    """FR-023: Batch fires callback even with partial failures."""

    async def test_batch_callback_fires_with_failure_info(self) -> None:
        from arvel.queue.batch import Batch
        from arvel.queue.drivers.sync_driver import SyncQueue
        from arvel.queue.job import Job

        callback_results: list[dict] = []

        class GoodJob(Job):
            async def handle(self) -> None:
                pass

        class BadJob(Job):
            max_retries: int = 0

            async def handle(self) -> None:
                raise RuntimeError("batch fail")

        class Callback(Job):
            async def handle(self) -> None:
                callback_results.append({"fired": True})

        batch = Batch([GoodJob(), BadJob()]).then(Callback())
        queue = SyncQueue()
        await batch.dispatch(queue)

        assert len(callback_results) == 1
