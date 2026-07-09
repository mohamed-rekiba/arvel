"""arvel.queue — the module-level lazy ``__getattr__`` re-exports and the ``--memory`` worker
stop valve (``_stop_on_memory``)."""

from __future__ import annotations

import asyncio

import pytest

import arvel.queue as queue_mod
from arvel.queue import _stop_on_memory  # pyright: ignore[reportPrivateUsage]


def test_lazy_module_reexports() -> None:
    from arvel.queue.batch import Batch, JobBatch

    assert queue_mod.Batch is Batch
    assert queue_mod.JobBatch is JobBatch
    with pytest.raises(AttributeError):
        _ = queue_mod.NotARealExport


async def test_stop_on_memory_signals_once_rss_exceeds_limit() -> None:
    stop = asyncio.Event()
    # limit 0 MB -> any RSS exceeds it, so the first poll sets the stop event and returns.
    await _stop_on_memory(stop, limit_mb=0, interval=0.001)
    assert stop.is_set()


def test_queue_manager_no_longer_defines_the_worker_loop_or_codec() -> None:
    """DR-0048/E14 V6 acceptance: the worker loop + serialization codec live in
    `queue/worker.py`/`queue/serialization.py`, not `queue/__init__.py` — `QueueManager` only
    *delegates* (`work` -> `self._worker.work`; enqueue/admin -> the split-out modules)."""
    from arvel.queue import QueueManager
    from arvel.queue.worker import JobWorker

    # `_runner`/`_invoke`/`_release_loop` are gone from both the module and the class — they were
    # QueueManager methods pre-extraction; `work` stays (a public delegator), the rest don't.
    for name in ("_runner", "_invoke", "_release_loop"):
        assert name not in vars(queue_mod), f"{name} must not be defined in queue/__init__.py"
        assert name not in vars(QueueManager), f"{name} must not be (re)defined on QueueManager"

    # `serialize`/`deserialize` resolve through `arvel.queue` (re-export completeness) but are
    # actually *defined* in `queue/serialization.py`, not redefined here.
    assert queue_mod.serialize.__module__ == "arvel.queue.serialization"
    assert queue_mod.deserialize.__module__ == "arvel.queue.serialization"
    assert queue_mod.run_job_with_retries.__module__ == "arvel.queue.worker"

    # `_invoke`/`_release_loop`/`ensure_task` (the former `_runner`) live on JobWorker instead.
    assert callable(JobWorker._invoke)  # pyright: ignore[reportPrivateUsage]
    assert callable(JobWorker._release_loop)  # pyright: ignore[reportPrivateUsage]
    assert callable(JobWorker.ensure_task)

    manager = QueueManager()
    assert isinstance(manager._worker, JobWorker)  # pyright: ignore[reportPrivateUsage]
    assert QueueManager.work is not JobWorker.work  # a thin delegator, not a copy
