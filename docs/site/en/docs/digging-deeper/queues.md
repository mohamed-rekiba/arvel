# Queues

Long-running work does not belong on the request thread. Arvel’s queue system wraps **`QueueContract`** with **`Job`** classes, **`Batch`** and **`Chain`** helpers, a central **`JobRunner`** (retries, timeouts, middleware), and first-class **middleware** for rate limiting, overlap protection, and uniqueness.

At **v0.1.0**, drivers include sync (for tests), null, and Taskiq-backed async execution—check your project’s `QueueSettings` for the exact default.

## Jobs

Subclass **`Job`** (a Pydantic model) and implement **`handle()`**. Configure retries, backoff (`int`, per-attempt list, or `"exponential"`), timeouts, queue name, and **uniqueness** via `unique_for`, `unique_id`, and `unique_until_processing`.

```python
from arvel.queue.job import Job


class SendWeeklyDigest(Job):
    max_retries: int = 5
    backoff: str = "exponential"
    queue_name: str = "mail"

    user_id: int

    async def handle(self) -> None:
        # Load user, render digest, enqueue mail — heavy work goes here
        ...
```

Override **`middleware()`** to return instances of **`JobMiddleware`** subclasses for cross-cutting behavior on this job only.

## Dispatching

Obtain **`QueueContract`** from the container and call **`dispatch`** with a job instance (exact signature follows your driver). The **`Scheduler`** uses the same contract to enqueue scheduled work.

## Batches and chains

- **`Batch`** — wrap several **`Job`** instances, dispatch them via the queue, record successes and failures in a **`BatchResult`**, and optionally run a **`then()`** callback job afterward
- **`Chain`** — dispatch jobs **one after another**, stopping if a job fails permanently after retries

Use these when orchestration beats ad-hoc `await` chains in application code but you still want **`QueueContract`** semantics.

## JobRunner

**`JobRunner`** is the execution engine: retries, backoff, timeout enforcement, middleware pipeline, and failure hooks (`on_failure`). Drivers delegate **`execute(job)`** here so behavior stays consistent regardless of backend.

## Middleware

Built-in middleware includes:

- **`RateLimited`** — cap executions per key within a sliding window
- **`WithoutOverlapping`** — hold a lock so only one copy of a logical job runs at a time
- **`UniqueJobGuard`** — prevents duplicate dispatches for jobs with uniqueness metadata, using your **`LockContract`**

```python
from arvel.lock.contracts import LockContract
from arvel.queue.middleware import RateLimited, WithoutOverlapping


class ImportRows(Job):
    async def middleware(self) -> list[object]:
        lock: LockContract = ...  # resolved from container in real code
        return [
            RateLimited(key="import", max_attempts=10, decay_seconds=60, lock=lock),
            WithoutOverlapping(key="import-global", lock=lock),
        ]

    async def handle(self) -> None: ...
```

## Laravel echoes

If you have written Laravel jobs with `$tries`, `backoff`, `middleware()`, and `ShouldBeUnique`, Arvel’s API rhymes with that mental model—async Python, explicit contracts, and middleware objects instead of method strings.

Queues are how you keep **latency predictable** and **failures visible**: failed job tables, retries, and observability hooks integrate at the runner level so you can sleep at night when traffic spikes.
