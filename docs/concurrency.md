# Concurrency

`Concurrency.run` runs a batch of zero-arg callables concurrently
and returns their results **in the same order you passed them** — regardless of which one finishes
first.

```python
from arvel.support import Concurrency

async def fetch_a(): ...
async def fetch_b(): ...

results = await Concurrency.run([fetch_a, fetch_b])   # [result_a, result_b], in that order
```

## Drivers

`driver` picks *how* each callable actually runs:

- **`"async"` (default)** — a coroutine-function is `await`-ed directly; a plain sync callable
  runs via `asyncio.to_thread` so it doesn't block the event loop. This is the right default for
  I/O-bound work (HTTP calls, DB queries) — you can freely mix async and sync callables in one
  call.
- **`"thread"`** — every callable runs via `asyncio.to_thread`, whether or not it's a coroutine
  function. Use this when you specifically want thread-based concurrency for sync work.
- **`"process"`** — every callable is offloaded to a real OS process
  (`concurrent.futures.ProcessPoolExecutor`, via `loop.run_in_executor`). This is the one driver
  that gives you **true CPU parallelism** — `asyncio.gather`/`to_thread` can't, because the GIL
  keeps only one thread executing Python bytecode at a time. Reach for it for CPU-bound work
  (image processing, heavy computation):

```python
import functools

def resize(path: str) -> str: ...

jobs = [functools.partial(resize, p) for p in image_paths]
results = await Concurrency.run(jobs, driver="process")
```

## The process driver's constraint: picklable callables

`ProcessPoolExecutor` sends each callable to a worker process by **pickling** it, so it must be
**module-level and picklable** — no lambdas, no closures, no bound methods on a local object.
`functools.partial` over a module-level function (as above) works fine, since `partial` objects
pickle their underlying function + arguments.

```python
# Works: module-level function (+ optional functools.partial for arguments)
def cpu_task(n: int) -> int: ...
await Concurrency.run([functools.partial(cpu_task, 1_000_000)], driver="process")

# Fails to pickle: a lambda or a closure
await Concurrency.run([lambda: cpu_task(1_000_000)], driver="process")   # don't do this
```

## Proof: the event loop isn't blocked

The value the `"process"` driver adds over `gather`/`to_thread` is real: while a CPU-bound
callable runs in a *separate process*, the event loop thread stays completely free to run other
`asyncio` tasks — including ones with their own timing, like a periodic ticker:

```python
async def ticker():
    for _ in range(10):
        await asyncio.sleep(0.05)
        record_tick()

ticker_task = asyncio.create_task(ticker())
await Concurrency.run([functools.partial(cpu_bound, huge_n)] * 2, driver="process")
await ticker_task
# the ticker's ticks land ~50ms apart the whole time — the loop was never blocked,
# even though two genuinely CPU-bound functions were running concurrently
```

## A worked example: assembling a dashboard

The everyday use of the default `"async"` driver is fanning out independent I/O and waiting on all of
it once, instead of `await`-ing each call in series. A dashboard that needs three unrelated things —
the user's orders, their unread notifications, and a billing summary — shouldn't pay for them one
after another:

```python
from functools import partial
from arvel.support import Concurrency

async def dashboard(request, user):
    orders, unread, billing = await Concurrency.run([
        partial(Order.where(user_id=user.id).get),      # DB query
        partial(notifications.unread_count, user),       # cache/DB
        partial(billing_api.summary, user.account_id),   # HTTP call
    ])
    return {"orders": orders, "unread": unread, "billing": billing}
```

The three calls run concurrently and the results come back **in the order you listed them** —
`orders`, `unread`, `billing` — no matter which finishes first, so you can unpack them positionally.
The total wait is roughly the slowest single call, not the sum of all three. Because the default
driver awaits coroutines directly and pushes plain sync callables onto a thread, you can mix an async
DB query, a sync cache read, and an HTTP call in one batch without thinking about which is which.

## Common mistakes & gotchas

- **Using `driver="process"` with a lambda or closure.** It'll fail with a pickling error — see
  above. Extract the work into a module-level function.
- **Reaching for `"process"` for I/O-bound work.** Spawning OS processes has real overhead; use
  the default `"async"` driver for anything that's mostly waiting on I/O.
- **Expecting cancellation to interrupt a running process-pool worker.** A hung CPU-bound task can
  outlive the caller's own cancellation — a documented limitation of `ProcessPoolExecutor` (see
  DR-0030). Keep process-pool callables bounded/well-behaved.

## How it works

`"async"` inspects each callable with `inspect.iscoroutinefunction` and either `await`s it or
routes it through `asyncio.to_thread`, then `asyncio.gather`s the lot — `gather` is what preserves
input order regardless of completion order. `"process"` does the same gather, but each callable
goes through `loop.run_in_executor` against a fresh `ProcessPoolExecutor` — stdlib only, zero new
dependency (chosen over `anyio.to_process` in DR-0030; revisit only if cancellation semantics
matter for your use case).

## See also

- [Processes](processes.md) — running *external commands*, as opposed to Python callables.
- [Queues & Jobs](queues.md) — for durable, retryable background work instead of in-request
  concurrency.
