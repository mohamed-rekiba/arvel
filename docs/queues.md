# Queues & Jobs

Some work is too slow to do inside a request: sending a welcome email, transcoding an upload,
calling a third-party API that takes seconds. Making the user wait for it is a bad trade. A **queue**
lets you hand that work off to run **in the background**, on a separate worker, so the request returns
immediately and the slow part happens out of band.

arvel's queue runs on [taskiq](https://taskiq-python.github.io). This page covers defining a job,
dispatching it, chaining and batching, retries and failure handling, and running a worker.

!!! note "Needs the `[queue]` extra"
    `uv add 'arvel[queue]'` gives you the core engine with the **in-memory** broker — fine for tests
    and a single process, but jobs are lost on restart and don't fan out to other workers. For real
    background processing pick a broker extra: `arvel[queue-redis]` (durable, multi-worker — the usual
    choice) or `arvel[queue-amqp]` (AMQP). See [Brokers](#brokers-memory-redis-amqp) below.

## Defining a job

Subclass `Job` and implement `handle()`:

```python
from arvel.queue import Job

class SendWelcomeEmail(Job):
    queue = "mail"      # which queue to run on (default: "default")
    tries = 3           # retry attempts before it's marked failed
    backoff = 5         # seconds between retries (or a list for per-attempt backoff)
    timeout = 60        # seconds before an attempt is aborted

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id

    async def handle(self) -> None:
        user = await User.find(self.user_id)
        await Mail.to(user).send(WelcomeMail())

    async def failed(self, exc: BaseException) -> None:
        # called once the job exhausts its retries
        log.error("welcome email failed", user_id=self.user_id, error=str(exc))
```

## Dispatching

```python
await SendWelcomeEmail.dispatch(user_id=42)
```

`dispatch` enqueues the job on the application's queue manager (or a default one outside an app
context) and returns immediately — the work runs on a worker, not in the request.

### Delayed dispatch

Run a job later instead of now (Laravel `dispatch()->delay()`) with `dispatch_after(seconds, …)`:

```python
await SendWelcomeEmail.dispatch_after(600, user_id=42)   # enqueue in 10 minutes
```

This is **durable**: instead of enqueuing immediately, it persists the job to the `jobs` table with
`available_at = now + delay` (the scaffold ships the migration). A running worker (`queue:work`) polls
for due rows and pushes them onto the broker when their time comes — so a delayed job survives a
restart. Delayed dispatch needs a configured database; without one it raises (dispatch immediately
instead). You can also release due jobs yourself: `await app.make("queue").release_due_jobs()`.

## Chaining & batching

Run several jobs in order, or fire a group at once, with `Bus`:

```python
from arvel.queue import Bus

# chain — sequential; each job is queued after the previous one
await Bus.chain([ResizeImage(id), Watermark(id), Notify(id)]).dispatch()

# batch — a group dispatched together; returns each push's handle
await Bus.batch([SendDigest(u.id) for u in users]).dispatch()
```

## Retries & failures

A job retries up to `tries` times, waiting `backoff` seconds between attempts. Provide a list for
escalating delays:

```python
class ChargeCard(Job):
    tries = 4
    backoff = [10, 30, 120]   # wait 10s, then 30s, then 120s
```

When every attempt fails, `failed()` is invoked so you can alert or record the failure.

### Failed jobs

After the retries are exhausted (and `failed()` has run), the worker records the dead job in the
`failed_jobs` table — the serialized payload, the exception, and when it failed (the scaffold ships
the migration). Inspect them and re-dispatch later, Laravel `queue:retry`-style:

```python
from arvel.queue import FailedJob

for job in await FailedJob.all():
    print(job.queue, job.exception, job.failed_at)

await job.retry()   # rebuilds the job, pushes it back onto the queue, and removes the record
```

Each row is a `FailedJob` (`arvel.queue.FailedJob`). With no database bound the worker still runs
`failed()` and simply skips persistence — nothing is lost, nothing crashes.

## Running a worker

Workers consume queued jobs out of process — the built-in one is the `queue:work` command:

```bash
arvel queue:work                 # consume jobs from the configured broker
```

Scale by running more worker processes (taskiq also ships its own worker for production). Whichever
worker picks up a job, it runs under that job's `tries`/`backoff`/`failed()` policy.

## Brokers (memory / redis / amqp)

The broker is chosen by the `queue` config — `default` names the driver, and `QUEUE_CONNECTION`
switches it at deploy time:

| Driver | Extra | When |
|--------|-------|------|
| `memory` | `arvel[queue]` | the zero-config default — in-process; great for tests/dev, **lost on restart** |
| `redis` | `arvel[queue-redis]` (`taskiq-redis`) | durable jobs, multiple workers (the usual production choice) |
| `amqp` | `arvel[queue-amqp]` (`taskiq-aio-pika`) | RabbitMQ/LavinMQ / any AMQP broker — when you want AMQP routing |

```python
# config/queue.py
config = {
    "default": env("QUEUE_CONNECTION", "memory"),   # memory | redis | amqp
    "url": env("QUEUE_URL", "redis://localhost:6379/0"),  # redis:// or amqp:// DSN for the active driver
}
```

`QueueManager` builds the matching taskiq broker from this config (an unknown driver raises a clear
error; a driver whose extra isn't installed tells you which to add). Pass a broker explicitly —
`QueueManager(broker=...)` — to override entirely (e.g. a Redis Stream or cluster broker).

## Common mistakes & gotchas

- **Passing a whole model to a job.** Jobs are serialized to JSON for the broker, so pass an **id**,
  not a loaded object, and re-fetch inside `handle()` for fresh data. (arvel serializes a model
  argument as a `(class, pk)` ref and re-loads it in the worker for you.)
- **Trusting the in-memory broker in production.** It's per-process and loses jobs on restart —
  switch to Redis before you depend on durability or multiple workers.
- **Swallowing failures.** Override `failed()` to alert or record; otherwise a job that exhausts its
  `tries` fails silently.
- **A `backoff` that hammers.** For flaky external calls use an escalating list (`[10, 30, 120]`) so
  retries back off instead of retrying instantly.

## How it works

`Job.dispatch(...)` serializes the job (model arguments become `(class, pk)` refs) and pushes it
onto the application's taskiq broker through the `QueueManager`; a single wrapper task runs it on the
worker, enforcing `tries`/`backoff` and calling `failed()` once retries are exhausted. taskiq is
imported lazily, so `import arvel` stays light until you actually queue something.

## See also

- [Events](events.md) — fire-and-forget *in-process* hooks (versus out-of-process jobs).
- [Mail](mail.md) · [Notifications](notifications.md) — common work to push onto a queue.
- [Console (CLI)](console.md) — `queue:work` and the scheduler.
