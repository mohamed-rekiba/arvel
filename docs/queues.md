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

Run a job later instead of now with `dispatch_after(seconds, …)`:

```python
await SendWelcomeEmail.dispatch_after(600, user_id=42)   # enqueue in 10 minutes
```

This is **durable**: instead of enqueuing immediately, it persists the job to the `jobs` table with
`available_at = now + delay` (the scaffold ships the migration). A running worker (`queue:work`) polls
for due rows and pushes them onto the broker when their time comes — so a delayed job survives a
restart. Delayed dispatch needs a configured database; without one it raises (dispatch immediately
instead). You can also release due jobs yourself: `await app.make("queue").release_due_jobs()`.

### After-commit dispatch

A job dispatched inside `db.transaction()` is normally enqueued **immediately** — a fast worker can
pick it up and look for a row the transaction hasn't committed yet. Opt into commit-anchored
dispatch per class or per call; the enqueue is then buffered and happens only after the outermost
commit (a rollback drops it, and outside a transaction it enqueues right away):

```python
class SendReceipt(Job):
    after_commit = True          # every dispatch of this class waits for the commit


async with db.transaction():
    order = await Order.create(...)
    await SendReceipt.dispatch(order.id)          # enqueued after COMMIT — worker sees the row
    await Reindex.dispatch_after_commit(order.id) # per-call form for a normally-eager job
```

A deferred dispatch returns `None` (there is no broker task yet). The deferral rides the event
dispatcher's [after-commit buffer](events.md) (the after-commit events section) — one seam
for events and jobs. Every buffered callback runs at flush even if an earlier one raises —
the data already committed, so one failing enqueue can't silently drop its siblings; the first
error still surfaces to the caller after the commit, and none of the work is retried.

### Routing by class

Declare which queue a job class lands on **centrally** — in a provider — instead of on every
class. Useful when the classes come from a package you don't own, or when queue topology is an
app decision, not a job decision:

```python
class AppServiceProvider(ServiceProvider):
    def boot(self) -> None:
        queue = self.app.make("queue")
        queue.route(SendReport, queue="reports")
        queue.route(RebuildIndex, queue="maintenance")
```

Precedence, most specific wins: an explicit `queue=` at dispatch > a `queue` attribute declared
on the job class **or any of its own ancestors below `Job`** (a subclass inherits its parent's
declared queue; only classes that never declared one fall through) > the route registry >
`"default"`. Registry lookups are exact-class — routing a base class does not route its
subclasses. Re-registering a class replaces its route. Every enqueue path resolves the same way:
immediate dispatch, delayed `dispatch_after`, retry-release, chains, and batches. arvel routes
the **queue label** only — the broker is one config-selected connection by design, so there is
no per-class connection routing.

## Chaining & batching

Run several jobs in order, or fire a group at once, with `Bus`:

```python
from arvel.queue import Bus

# chain — strictly sequential: job N+1 only starts once N has *succeeded*; a failure stops the
# rest of the chain (they never run)
await Bus.chain([ResizeImage(id), Watermark(id), Notify(id)]).dispatch()

# batch — a group dispatched together, tracked as a whole
batch = await Bus.batch([SendDigest(u.id) for u in users]).dispatch()
```

Only the head job is pushed to the broker right away — the remaining links travel serialized on
it, and the worker dispatches each next link once the prior one's `handle()` returns without
raising. Run something when the chain gives up with `catch` — it must be a **module-level
function** (a lambda/closure can't survive serialization onto the job):

```python
def alert_pipeline_failed(exc: BaseException) -> None:
    log.error("image pipeline failed", error=str(exc))

chain = Bus.chain([ResizeImage(id), Watermark(id), Notify(id)]).catch(alert_pipeline_failed)
await chain.dispatch()
```

### Batches: progress, callbacks, cancellation

`Bus.batch([...])` creates a `job_batches` row (the scaffold ships its migration) up front, then
pushes every job with the batch id riding along on it — so the worker can track completion as
they run, in any order, on any worker:

```python
def all_digests_sent(batch) -> None:
    log.info("digest batch done", batch_id=batch.id)

def a_digest_failed(batch, exc: BaseException) -> None:
    log.error("digest batch failed", error=str(exc))

def digests_settled(batch) -> None:
    log.info("digest batch settled", cancelled=batch.cancelled())

batch = await (
    Bus.batch([SendDigest(u.id) for u in users])
    .then(all_digests_sent)      # every job succeeded
    .catch(a_digest_failed)      # the first disallowed failure
    .finally_(digests_settled)   # always, once the batch finishes
    .name("weekly-digest")
    .dispatch()
)
```

`then`/`catch`/`finally_` callbacks must be **module-level functions**, same as a chain's `catch`
(a lambda/closure can't survive serialization). `then(batch)` fires once every job has succeeded;
`catch(batch, exc)` fires on the batch's **first** failure and cancels it — the rest of the queued
jobs no-op instead of running (still counted, so the batch still reaches 100%); `finally_(batch)`
always fires once, whether the batch finished cleanly or was cancelled. `allow_failures()` turns
off the cancel-on-failure behavior: the remaining jobs keep running, and `then` still fires once
everything has settled (`catch` never does).

`batch` (a `Batch` handle) exposes:

```python
await batch.progress()    # 0..100 — percent of jobs processed
await batch.total_jobs()
await batch.pending_jobs()
await batch.failed_jobs()
await batch.counts()      # {"total", "pending", "failed", "processed"}
await batch.finished()    # every job has settled
await batch.cancelled()   # a disallowed failure cancelled it
await batch.cancel()      # cancel it yourself — idempotent
```

**Atomic counters, not a lost-update race.** Two jobs can settle at the same instant on two
different workers; `pending_jobs`/`failed_jobs` are updated with an **atomic column expression**
(`UPDATE ... SET pending_jobs = pending_jobs - 1` — the database does the arithmetic, so
concurrent settles serialize on the row), and the finish/cancel transitions stay guarded by
`WHERE <timestamp> IS NULL`, so a decrement is never silently lost and `then`/`catch`/`finally_`
each fire **exactly once**, never twice.

## Unique jobs

`ShouldBeUnique` caps a job to **at most one** queued/running instance at a time — a second
dispatch while one is already in flight is silently dropped:

```python
from arvel.queue.middleware import ShouldBeUnique

class GenerateInvoice(Job, ShouldBeUnique):
    unique_for = 3600  # the lock's TTL (seconds) — a safety net if a worker dies mid-run

    def __init__(self, order_id: int) -> None:
        self.order_id = order_id

    def unique_id(self) -> str:
        return str(self.order_id)   # scope uniqueness per order, not per class

    async def handle(self) -> None:
        ...
```

Before dispatch, `Job.dispatch()` acquires a `CacheLock` keyed by the job's class +
`unique_id()`; a second `dispatch()` for the same key while it's held returns `None` (nothing
enqueued) instead of raising. The lock is released once the worker finishes processing the job —
or after `unique_for` seconds, whichever comes first, so a crashed worker can't wedge it forever.

## Job middleware

Override `middleware()` on a job to run its `handle()` through a small onion pipeline (the same
shape as HTTP middleware) before it actually executes:

```python
from arvel.queue.middleware import RateLimited, WithoutOverlapping

class SyncInventory(Job):
    def __init__(self, warehouse_id: int) -> None:
        self.warehouse_id = warehouse_id

    def middleware(self) -> list:
        return [WithoutOverlapping(f"warehouse:{self.warehouse_id}", expire=300, release_after=5)]

    async def handle(self) -> None:
        ...
```

- **`WithoutOverlapping(key, expire=60, release_after=0)`** — serializes jobs sharing `key`: a run
  that finds the lock already held is released back onto the queue (after `release_after`
  seconds) instead of running now; `expire` bounds a stuck holder that dies without releasing.
- **`RateLimited(limiter, key, max_attempts, decay_seconds=60)`** — caps executions sharing `key`
  to `max_attempts` per window (`limiter` is an `arvel.http.rate_limiter.RateLimiter`); over the
  limit, the job is deferred rather than run.
- **`ThrottlesExceptions(max_exceptions, decay_seconds=60, key=None)`** — a small circuit breaker:
  once `max_exceptions` failures land within the window, further attempts are deferred immediately
  instead of calling `handle()` (and failing again).

All three defer by raising internally and re-enqueuing the job after a delay — durable (the `jobs`
table) when a database is bound, mirroring the retry-release mechanism above; an inline
sleep-then-repush otherwise. A deferral never counts against a job's `tries`.

## Retries & failures

A job retries up to `tries` times. `max_exceptions` is an extra, lower ceiling on attempts (handy
when `tries` is generous but you still want to give up sooner); `retry_until` stops retrying past a
fixed point in time regardless of `tries` left:

```python
class ChargeCard(Job):
    tries = 4
    backoff = [10, 30, 120]        # wait 10s, then 30s, then 120s
    max_exceptions = 2             # give up after 2 failures even though tries=4
    retry_until = datetime(2026, 1, 1)  # never retry past this moment
```

When every attempt fails, `failed()` is invoked so you can alert or record the failure.

### How a retry actually waits: release vs. inline sleep

On a **durable** setup (a database bound — the `jobs` table backs this regardless of which broker
carries messages), a failed attempt is **released back to the queue store** with
`available_at = now + backoff` instead of blocking the worker with `asyncio.sleep`: the worker
keeps draining other jobs, and a later pass (`release_due_jobs`, run periodically by `queue:work`)
redispatches it once due. The attempt count travels with the job across these passes, so
`tries`/`backoff` are honored exactly the same either way — just without stalling the worker.

Without a database bound (the common in-memory/dev setup), there's nowhere to persist a release, so
the worker falls back to the classic **inline** loop: every attempt happens in one call,
`asyncio.sleep`-ing between them. Fine for a single dev process; not what you want in production,
where a slow backoff would otherwise stall the whole worker.

### Job timeout

`timeout` (seconds) bounds each attempt via `asyncio.wait_for` — an attempt that runs past it is
cancelled (cooperatively; the coroutine gets `asyncio.CancelledError`) and the timeout counts as a
failed attempt, retried/failed exactly like a raised exception.

### Visibility timeout (recovering from a crashed worker)

A worker that claims a delayed/released job (`reserved_at` set) but crashes before finishing would
otherwise leak that row forever. `retry_after` (seconds — the `queue.retry_after` config, default
`90`; override per job with a `retry_after` class attribute) is the **visibility timeout**: once a
reservation is older than that, `release_due_jobs` reclaims it (clears `reserved_at`) so the next
pass picks it back up. A worker still legitimately working a job well within `retry_after` is left
alone. (Internally the effective deadline is stamped as `reserved_until` at claim time, so reclaim
is a single indexed lookup — the per-job `retry_after` override still applies exactly as described.)

A row whose payload can no longer be decoded — a job class renamed or removed between enqueue and
release — is **quarantined**, not left to block the queue: it's claimed, logged
(`undeserializable_job`), and left for the visibility timeout to retry or age into failure, while
the rest of the batch keeps draining.

### Failed jobs — the dead-letter queue (DLQ)

When a job **exhausts its retries** (or gives up early — `fail_on_timeout`, or a passed
`retry_until`), the worker runs the job's `failed(exc)` hook and then records it in the
`failed_jobs` table: the queue, the serialized payload, the exception text, and when it failed. This
is arvel's **dead-letter queue** — nothing is silently dropped; a dead job waits there for you to
inspect, fix, and requeue (the scaffold ships the migration).

**From the CLI** (the usual path):

```bash
arvel queue:failed            # list the dead-letter jobs — id, queue, exception, failed_at
arvel queue:retry <id>        # re-dispatch one job (fresh tries budget) and remove its record
arvel queue:retry all         # re-dispatch every dead-letter job
```

**From code** — `FailedJob` (`arvel.queue.FailedJob`) is an ordinary model, so you inspect and act
on the DLQ like any table:

```python
from arvel.queue import FailedJob

for job in await FailedJob.order_by("failed_at", "desc").get():
    print(job.id, job.queue, job.exception, job.failed_at)   # triage

await some_failed_job.retry()      # rebuild + re-push with a full tries budget, then delete the record
await some_failed_job.delete()     # …or discard it for good once you've decided it's unrecoverable
```

A retry is a **fresh dispatch** — the exhausted attempt counter is reset, so a requeued job gets its
whole `tries`/`backoff` budget again (it won't bounce straight back to the DLQ). Fix the root cause
first (the bug, the missing downstream) — a blind `queue:retry all` just re-fails everything.

Monitor the table's size (a growing DLQ means something downstream is broken) and prune records
you've resolved with a normal delete. With **no database bound**, the worker still runs `failed()`
but skips persistence — nothing crashes, but there's no DLQ to retry from, so bind a DB in
production.

## Running a worker

Workers consume queued jobs out of process — the built-in one is the `queue:work` command:

```bash
arvel queue:work                 # consume jobs from the configured broker
```

Scale by running more worker processes (taskiq also ships its own worker for production). Whichever
worker picks up a job, it runs under that job's `tries`/`backoff`/`timeout`/`failed()` policy.

### Worker flags

`QueueManager.work(...)` (what `queue:work` calls) takes the same lifecycle flags, for a custom
worker entrypoint/supervisor script:

```python
await app.make("queue").work(
    max_jobs=100,        # stop after 100 jobs processed
    max_time=3600,       # stop after an hour (a supervisor restarts it)
    stop_when_empty=True,  # stop once idle instead of running forever
    rest=1,              # pause 1s between jobs (ease off a hammered downstream)
    memory=512,          # stop if RSS exceeds 512MB (a supervisor restarts it fresh)
)
```

Ctrl-C (`SIGINT`) or `SIGTERM` request the same **graceful** stop regardless of which flags are
set: the in-flight job finishes before the worker exits — nothing is left half-run. Run it under a
process supervisor (systemd/supervisord/your platform's process manager) that restarts it when it
stops, and these flags become "restart periodically" knobs rather than a way to lose work.

## Context in a job

A value set with `Context` (see [Context](context.md)) at dispatch time is carried across the
broker and restored before `handle()` runs — a request-scoped value (a tenant id, a correlation id)
set before you dispatch is still there inside the job, even on a different worker process:

```python
from arvel.support.context import Context

Context.add("tenant", tenant.id)
await SendWelcomeEmail.dispatch(user_id=42)   # "tenant" rides along in the job payload

class SendWelcomeEmail(Job):
    async def handle(self) -> None:
        tenant_id = Context.get("tenant")     # the *dispatch-time* value, not whatever's ambient
        ...
```

### Log correlation

Separately from `Context`, a job's **logs** are correlated for you. When you dispatch a job, the
dispatcher's whole bound log context (a request's `request_id`, plus anything else it bound —
`user_id`, `tenant_id`, …) is captured and re-bound on the worker, and the job also gets its own
fresh `job_id` (a `uuidv7`). So every log line a job emits carries the `request_id` of the API
request that spawned it *and* its own `job_id` — you can trace one request to every job it dispatched.
See [Logging → Request & queue correlation](logging.md#request--queue-correlation). (Use `Context`
for values your job *logic* reads; this is automatic, for *logs*.)

## Queued event listeners

An event listener marked `ShouldQueue` (see [Events](events.md)) runs on the queue instead of
inline — the event dispatcher enqueues it through the same broker as everything else, and a worker
runs it under the normal `tries`/`backoff`/`timeout` policy. This needs the queue provider
registered (it binds the `queue_dispatcher` seam the event dispatcher calls); without one, a queued
listener still runs — inline, same as a plain listener — rather than silently vanishing.

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

- [Events](events.md) — fire-and-forget *in-process* hooks (versus out-of-process jobs), and the
  `ShouldQueue` listener rail this page's [Queued event listeners](#queued-event-listeners) covers.
- [Context](context.md) — the ambient key/value store this page's [Context in a job](#context-in-a-job)
  carries across the broker.
- [Mail](mail.md) · [Notifications](notifications.md) — common work to push onto a queue.
- [Console (CLI)](console.md) — `queue:work` and the scheduler.
- [Telemetry](telemetry.md) — when telemetry is on, each job run is auto-traced as a `job <Name>` span
  (and nests under the dispatching request when it runs inline).
