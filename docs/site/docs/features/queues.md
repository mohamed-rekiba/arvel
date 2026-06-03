# Queues

<a name="introduction"></a>
## Introduction

While building your application, some tasks — parsing an uploaded file, sending email — take too long to do during a typical web request. Arvel lets you push these onto a queue so they run in a background worker, keeping requests fast. **Jobs** describe the work; the `Bus` facade dispatches them; a **worker** processes them.

<a name="configuration"></a>
## Configuration

Queues read `config/queue.py` — `default` picks the active connection. The `QUEUE_*` environment variables are the fallback when a key isn't in the file (see [the cascade](../core-concepts/configuration.md#the-cascade)):

```ini
QUEUE_CONNECTION=database
```

<a name="backends"></a>
### Backends

| Backend | Behavior |
|---|---|
| `sync` | Runs jobs immediately, in-process — no worker needed (development) |
| `database` | Persists jobs to a table; a worker pulls them |
| `redis` | Uses Redis as the broker; requires `arvel[redis]` |
| `taskiq` | Integrates with the TaskIQ ecosystem |

<a name="registering-the-provider"></a>
### Registering the Provider

Queues are **opt-in**. Add `QueueServiceProvider` to `bootstrap/providers.py`. It binds the `Bus` facade and registers the queue CLI commands.

<a name="creating-jobs"></a>
## Creating Jobs

<a name="job-structure"></a>
### Job Structure

A job is a Pydantic model that subclasses `Job`. Declare its payload as typed fields and implement an async `handle`. Jobs auto-register so the worker can rebuild them from the wire payload:

```python
from arvel.queue.job import Job


class ProcessPodcast(Job):
    podcast_id: int

    async def handle(self) -> None:
        # do the slow work
        ...
```

<a name="job-options"></a>
### Job Options

Tune execution by setting fields on the job. These are envelope metadata, separate from your payload:

| Field | Default | Meaning |
|---|---|---|
| `queue` | `"default"` | The queue name to route to |
| `tries` | `3` | Maximum attempts before the job fails |
| `timeout` | `60` | Seconds before an attempt is considered timed out |
| `delay` | `0` | Seconds (or a `timedelta`) to wait before the job becomes available |
| `priority` | `0` | `0`–`9`; out-of-range values are rejected |
| `backoff` | `0` | Seconds between retries; a list sets per-attempt delays |
| `retry_until` | `None` | A `datetime` deadline — jobs past it go straight to the dead-letter queue |

```python
class ProcessPodcast(Job):
    podcast_id: int
    queue: str = "media"
    tries: int = 5
    backoff: list[int] = [30, 60, 120]
```

<a name="dispatching-jobs"></a>
## Dispatching Jobs

Dispatch a job instance through the `Bus` facade. `dispatch` is a coroutine:

```python
from arvel.facades.bus import Bus

await Bus.dispatch(ProcessPodcast(podcast_id=1))
```

<a name="delayed-dispatch"></a>
### Delayed Dispatch

Set `delay` to defer availability:

```python
from datetime import timedelta

await Bus.dispatch(ProcessPodcast(podcast_id=1, delay=timedelta(minutes=10)))
```

<a name="batches-and-chains"></a>
### Batches & Chains

Dispatch many jobs together, or enqueue them in order:

```python
await Bus.batch([ProcessPodcast(podcast_id=i) for i in range(10)])
await Bus.chain([NormalizeAudio(podcast_id=1), Transcode(podcast_id=1)])
```

> [!NOTE]
> `Bus.chain([...])` enqueues the jobs in order — it does not wait for one to finish before the next runs or stop the chain on failure. Use it for ordered submission, not strict sequential execution.

<a name="running-the-worker"></a>
## Running the Worker

For any backend other than `sync`, run a worker process to pull and execute jobs:

```bash
arvel queue:work
arvel queue:work --queue=media       # only the media queue
```

<a name="retries-and-backoff"></a>
## Retries & Backoff

When a job raises, the worker retries it up to `tries` times. `backoff` controls the wait between attempts — a single value applies to every retry, a list applies per attempt (the last value repeats once exhausted). A job whose `retry_until` deadline has passed skips remaining retries and goes to the dead-letter queue.

<a name="failed-jobs"></a>
## Failed Jobs

Inspect and re-run jobs that exhausted their retries:

```bash
arvel queue:failed            # list failed jobs
arvel queue:retry <uuid>      # re-dispatch a failed job by UUID
arvel queue:forget <uuid>     # delete a single failed job
arvel queue:flush             # clear the failed-job table
arvel queue:size              # count pending jobs on a queue
```
