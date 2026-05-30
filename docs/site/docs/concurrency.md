# Concurrency

Arvel is async-native — every layer (routing, ORM, cache, queues, mail) is written for `asyncio`. Use the standard library primitives directly; there's no Arvel-specific concurrency helper.

## Running tasks in parallel

```python
import asyncio


async def fan_out():
    results = await asyncio.gather(
        fetch_user(1),
        fetch_user(2),
        fetch_user(3),
    )
    return results
```

For bounded concurrency (e.g., "at most 10 in flight at once"), use a semaphore:

```python
sem = asyncio.Semaphore(10)


async def bounded(coro):
    async with sem:
        return await coro


results = await asyncio.gather(*(bounded(fetch_user(i)) for i in user_ids))
```

## Async TaskGroup (Python 3.11+)

```python
async with asyncio.TaskGroup() as tg:
    a = tg.create_task(fetch_user(1))
    b = tg.create_task(fetch_user(2))

print(a.result(), b.result())
```

`TaskGroup` propagates exceptions cleanly and cancels siblings on failure.

## Background tasks after the response

```python
from starlette.background import BackgroundTask


@Route.post("/users")
async def create_user(...) -> Response:
    user = await User.create(...)
    return JSONResponse(
        {"id": user.id},
        background=BackgroundTask(send_welcome_email, user.id),
    )
```

For anything heavier than a single after-response side effect, dispatch a [queued job](queues.md) instead.

## Process-level concurrency

For CPU-bound work, dispatch to a process pool:

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor

executor = ProcessPoolExecutor()


async def cpu_bound(payload):
    return await asyncio.get_running_loop().run_in_executor(executor, heavy_compute, payload)
```

## See also

- [Queues](queues.md) — for fire-and-forget background work.
