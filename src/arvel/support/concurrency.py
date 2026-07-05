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
    async def run(callables: Sequence[Callable[[], Any]], driver: Driver = "async") -> list[Any]:
        if driver == "async":
            return await Concurrency._run_async(callables)
        if driver == "thread":
            return list(await asyncio.gather(*(asyncio.to_thread(fn) for fn in callables)))
        if driver == "process":
            return await Concurrency._run_process(callables)
        raise ValueError(f"unknown concurrency driver: {driver!r}")

    @staticmethod
    async def _run_async(callables: Sequence[Callable[[], Any]]) -> list[Any]:
        async def call_one(fn: Callable[[], Any]) -> Any:
            if inspect.iscoroutinefunction(fn):
                return await fn()
            return await asyncio.to_thread(fn)

        return list(await asyncio.gather(*(call_one(fn) for fn in callables)))

    @staticmethod
    async def _run_process(callables: Sequence[Callable[[], Any]]) -> list[Any]:
        loop = asyncio.get_running_loop()
        # a fresh pool per call keeps lifecycle simple; worker-spawn cost is acceptable for
        # coarse CPU jobs — share an executor at the call site if invoked hot
        with ProcessPoolExecutor() as pool:
            return list(await asyncio.gather(*(loop.run_in_executor(pool, fn) for fn in callables)))
