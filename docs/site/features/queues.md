# Queues

<a name="introduction"></a>
## Introduction

While building your application, some tasks — parsing an uploaded file, sending email — take too long to do during a typical web request. Arvel lets you push these onto a queue so they run in a background worker, keeping requests fast. **Jobs** describe the work; the `Bus` facade dispatches them; a **worker** processes them.

<a name="quick-start"></a>
### Quick start

Register the provider, define a job, dispatch it, and run a worker:

```python
# bootstrap/providers.py
from arvel.queue.providers.queue_service_provider import QueueServiceProvider

providers = [QueueServiceProvider, ...]
```

```python
# app/jobs/process_podcast.py
from arvel.queue.job import Job


class ProcessPodcast(Job):
    podcast_id: int

    async def handle(self) -> None:
        ...
```

```python
from arvel.facades.bus import Bus

await Bus.dispatch(ProcessPodcast(podcast_id=1))
```

```bash
# database driver — publish migrations, migrate, then work
arvel vendor:publish --tag=arvel-queue
arvel migrate
arvel queue:work
```

> [!NOTE]
> The default connection is `sync`, which runs jobs inline — fine for local dev and tests. Switch to `database` or `redis` when you need a real worker. See [Configuration](#configuration).

Typical request → queue flow:

```python
async def upload_podcast(request: UploadRequest) -> PodcastResponse:
    podcast = await Podcast.create(...)
    await Bus.dispatch(ProcessPodcast(podcast_id=podcast.id))
    return PodcastResponse(id=podcast.id, status="processing")
```

The HTTP response returns immediately; `ProcessPodcast.handle()` runs in a worker process.

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

Queues are **opt-in**. Add `QueueServiceProvider` to `bootstrap/providers.py`. It binds the `Bus` facade, registers the queue CLI commands, and publishes the jobs / failed-jobs migrations (`arvel vendor:publish --tag=arvel-queue`). See [Service Providers](../core-concepts/service-providers.md#opt-in-providers).

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

<a name="dispatch-many-and-chains"></a>
### Dispatching Many Jobs & Chains

Fan out a batch of independent jobs with `dispatch_many` — they run in parallel as workers pick them up — or sequence them with `chain` so each one waits for the previous to finish:

```python
# Fan-out: ten jobs go on the queue; workers run them concurrently.
await Bus.dispatch_many([ProcessPodcast(podcast_id=i) for i in range(10)])

# Chain: Transcode only runs after NormalizeAudio finishes successfully.
# If NormalizeAudio fails (after retries), Transcode is never dispatched.
await Bus.chain([NormalizeAudio(podcast_id=1), Transcode(podcast_id=1)])
```

Chains carry their tail on the head envelope: when the worker finishes job N successfully, it dispatches job N+1; when N fails terminally, the rest of the chain is dropped. The `sync` driver runs chains inline for the same effect during tests.

<a name="running-the-worker"></a>
## Running the Worker

For any backend other than `sync`, run a worker process to pull and execute jobs:

```bash
arvel queue:work
arvel queue:work --queue=media              # only the media queue
arvel queue:work --stop-when-empty          # drain the queue once, then exit (CI / one-shot)
```

### Graceful restart after a deploy

After a code change, running workers still hold the **old** code in memory. Trigger a clean restart with:

```bash
arvel queue:restart
```

That writes a UTC timestamp to a cache key (`arvel:queue:restart`) that every `queue:work` process checks between jobs. Workers finish whatever they're running and exit cleanly; your process manager (systemd, supervisor, k8s) brings them back up on the new code. No jobs are lost or duplicated — they go back on the queue if the worker exits mid-handle.

> [!WARNING]
> `queue:restart` needs a bound [cache](../features/cache.md) store so the signal reaches workers. Without `CacheServiceProvider`, the command still runs but the marker is a no-op and workers won't restart.

Cancelling a worker (task cancellation, `SIGINT`) is **not** a job failure. The cancellation propagates and the worker stops — the in-flight job is never sent to the dead-letter queue or counted as a failed attempt. Only a real exception from `handle()` or a per-job `timeout` marks a job as failed.

<a name="reliability"></a>
### Reliability (at-least-once delivery)

The `database` driver reserves a job instead of deleting it on pop. The worker deletes the row only after the job finishes — succeeds, exhausts retries, or lands in the dead-letter queue. If the worker is killed mid-handle (OOM, `SIGKILL`, node loss), the row stays reserved and becomes claimable again once its visibility timeout lapses, so the job redelivers rather than vanishing.

`retry_after` sets that timeout in seconds (default `90`). Set it comfortably above your longest job's worst-case runtime — otherwise a slow job can be picked up by a second worker while the first is still running it.

```ini
QUEUE_DATABASE_RETRY_AFTER=90
```

This is at-least-once delivery: a crash at the wrong moment can redeliver a job that already ran. Make handlers idempotent (guard on a unique key, upsert instead of insert) so a redelivery is harmless.

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

<a name="testing"></a>
## Testing

`Bus.fake()` records dispatches without executing jobs — use it to assert side effects were queued, not run:

```python
from arvel.facades.bus import Bus

with Bus.fake():
    await upload_podcast(request)
    Bus.assert_dispatched(ProcessPodcast)
    Bus.assert_dispatched_on(ProcessPodcast, "media")
    Bus.assert_not_dispatched(DeletePodcast)
```

For chains:

```python
with Bus.fake():
    await Bus.chain([NormalizeAudio(podcast_id=1), Transcode(podcast_id=1)])
    Bus.assert_chained(NormalizeAudio, Transcode)
```

See also [Events](events.md#queued-listeners) (queued listeners dispatch via `Bus`) and [Scheduling](scheduling.md#scheduling-jobs-and-commands) (`schedule.job(...)` dispatches through the same bus).
