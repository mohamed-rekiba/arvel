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
