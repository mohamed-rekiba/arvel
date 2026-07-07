"""arvel.support.concurrency — offload a batch of callables concurrently (`Concurrency`
parity), results returned in call order regardless of completion order.

Default driver `"async"`: coroutine-functions are gathered directly; sync callables run via
`asyncio.to_thread`. Driver `"thread"` forces every callable through a thread. Driver `"process"`
offloads to a `concurrent.futures.ProcessPoolExecutor` via `loop.run_in_executor` — real CPU
parallelism, the one thing `gather`/`to_thread` can't give (DR-0030: stdlib `ProcessPoolExecutor`
over `anyio.to_process`, zero new dep). Callables passed to the `"process"` driver must be
module-level and picklable.

    results = await Concurrency.run([job1, job2])                 # ordered results
    results = await Concurrency.run(sync_fns, driver="process")   # CPU-bound offload
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Literal

type Driver = Literal["async", "thread", "process"]


class Concurrency:
    """Static namespace for running a batch of zero-arg callables concurrently."""

    @staticmethod
    async def run(
        callables: Sequence[Callable[[], Any]] | dict[str, Callable[[], Any]],
        driver: Driver = "async",
        timeout: float | None = None,
    ) -> list[Any] | dict[str, Any]:
        """Run every callable concurrently under ``driver``, in call order. A ``dict``
        input returns a same-keyed ``dict`` of results (a ``list`` input stays a
        ``list``). ``timeout`` (seconds), if given, bounds each task individually —
        raises ``TimeoutError`` the moment any one task overruns it. Siblings are not
        cancelled on that first failure (and thread/process work can't be) — they run
        to completion in the background; their results are discarded."""
        if isinstance(callables, dict):
            keys: list[str] | None = list(callables.keys())
            jobs: Sequence[Callable[[], Any]] = list(callables.values())
        else:
            keys = None
            jobs = callables
        if driver == "async":
            results = await Concurrency._run_async(jobs, timeout)
        elif driver == "thread":
            results = list(
                await asyncio.gather(
                    *(Concurrency._bounded(asyncio.to_thread(fn), timeout) for fn in jobs)
                )
            )
        elif driver == "process":
            results = await Concurrency._run_process(jobs, timeout)
        else:
            raise ValueError(f"unknown concurrency driver: {driver!r}")
        return dict(zip(keys, results, strict=True)) if keys is not None else results

    @staticmethod
    async def _bounded(awaitable: Any, timeout: float | None) -> Any:
        """Await ``awaitable``, bounded by ``timeout`` seconds if given."""
        if timeout is None:
            return await awaitable
        return await asyncio.wait_for(awaitable, timeout)

    @staticmethod
    async def _run_async(
        callables: Sequence[Callable[[], Any]], timeout: float | None = None
    ) -> list[Any]:
        async def call_one(fn: Callable[[], Any]) -> Any:
            coro = fn() if inspect.iscoroutinefunction(fn) else asyncio.to_thread(fn)
            return await Concurrency._bounded(coro, timeout)

        return list(await asyncio.gather(*(call_one(fn) for fn in callables)))

    @staticmethod
    async def _run_process(
        callables: Sequence[Callable[[], Any]], timeout: float | None = None
    ) -> list[Any]:
        loop = asyncio.get_running_loop()
        # a fresh pool per call keeps lifecycle simple; worker-spawn cost is acceptable for
        # coarse CPU jobs — share an executor at the call site if invoked hot
        with ProcessPoolExecutor() as pool:
            return list(
                await asyncio.gather(
                    *(
                        Concurrency._bounded(loop.run_in_executor(pool, fn), timeout)
                        for fn in callables
                    )
                )
            )
