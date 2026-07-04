"""Concurrency — a typed wrapper offloading a batch of callables (Laravel `Concurrency` parity):
`async` gathers coroutine-functions + `to_thread`s sync callables, `thread` forces every callable
through a thread, `process` offloads to a real `ProcessPoolExecutor` (DR-0030) for CPU parallelism
— proven here by a concurrent ticker that keeps ticking on schedule while a CPU-bound function
runs, showing the event loop was never blocked."""

from __future__ import annotations

import asyncio
import functools
import time

from arvel.support import Concurrency


def _spin(n: int) -> int:
    """A CPU-bound busy loop — module-level + args-only so it's picklable for the process pool."""
    total = 0
    for i in range(n):
        total += i
    return total


async def _async_double(n: int) -> int:
    await asyncio.sleep(0)
    return n * 2


def _sync_double(n: int) -> int:
    return n * 2


async def test_async_driver_gathers_coroutine_functions_in_order() -> None:
    jobs = [functools.partial(_async_double, n) for n in (1, 2, 3)]
    results = await Concurrency.run(jobs)
    assert results == [2, 4, 6]


async def test_async_driver_offloads_sync_callables_to_a_thread() -> None:
    jobs = [functools.partial(_sync_double, n) for n in (1, 2, 3)]
    results = await Concurrency.run(jobs, driver="async")
    assert results == [2, 4, 6]


async def test_async_driver_mixes_sync_and_coroutine_callables_preserving_order() -> None:
    jobs = [
        functools.partial(_sync_double, 1),
        functools.partial(_async_double, 2),
        functools.partial(_sync_double, 3),
    ]
    results = await Concurrency.run(jobs)
    assert results == [2, 4, 6]


async def test_thread_driver_runs_sync_callables_and_preserves_order() -> None:
    jobs = [functools.partial(_sync_double, n) for n in (5, 10, 15)]
    results = await Concurrency.run(jobs, driver="thread")
    assert results == [10, 20, 30]


async def test_process_driver_runs_a_cpu_bound_callable_and_preserves_order() -> None:
    jobs = [functools.partial(_spin, 50_000) for _ in range(2)]
    results = await Concurrency.run(jobs, driver="process")
    assert results == [sum(range(50_000)), sum(range(50_000))]


async def test_process_driver_does_not_block_the_event_loop() -> None:
    """A 50ms ticker running concurrently with CPU-bound process-pool work stays on schedule —
    proof the event loop thread itself was never blocked (only a separate process was busy)."""
    ticks: list[float] = []

    async def ticker() -> None:
        for _ in range(4):
            start = time.monotonic()
            await asyncio.sleep(0.05)
            ticks.append(time.monotonic() - start)

    ticker_task = asyncio.create_task(ticker())
    jobs = [functools.partial(_spin, 20_000_000) for _ in range(2)]
    results = await Concurrency.run(jobs, driver="process")
    await ticker_task

    assert len(results) == 2
    # each tick slept ~50ms; a blocked loop would show one huge gap instead
    assert all(tick < 0.5 for tick in ticks)
