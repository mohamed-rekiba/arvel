# Queues

Queues let you defer time-consuming work — sending email, processing uploads, calling external APIs — to background workers. The user gets a fast response; the work happens later.

Arvel's queue layer is a typed, async-native take on Laravel's `Bus`. Jobs are Pydantic models. The dispatcher serializes them, ships them to a broker, and workers run them when capacity is available.

## Configuration

```env
QUEUE_DEFAULT=redis

QUEUE_CONNECTIONS_REDIS_DRIVER=redis
QUEUE_CONNECTIONS_REDIS_URL=redis://localhost:6379/1

QUEUE_CONNECTIONS_SQL_DRIVER=database
QUEUE_CONNECTIONS_SQL_TABLE=jobs

QUEUE_CONNECTIONS_SYNC_DRIVER=sync
```

Available drivers:

| Driver | Best for |
|---|---|
| `sync` | Tests, dev — runs jobs inline |
| `database` | Production without Redis |
| `redis` | Production with Redis available |
| `taskiq` | Production with Taskiq broker (RabbitMQ, NATS, etc.) |
| `null` | Discards |

## Defining a Job

```python
from arvel.queue import Job


class SendWelcomeEmail(Job):
    user_id: int
    locale: str = "en"

    queue = "emails"      # which queue to land on
    tries = 3             # max retry attempts
    timeout = 60          # seconds before the worker cancels the job (enforced)
    backoff = 30          # seconds to wait before each retry
    retry_until = None    # optional datetime — stop retrying after this time

    async def handle(self) -> None:
        user = await User.find_or_fail(self.user_id)
        await Mail.to(user.email).send(WelcomeMail(user, locale=self.locale))
```

Because `Job` is a Pydantic model, every field you declare becomes part of the job payload and gets validated when the worker dequeues.

### Job class attributes

| Attribute | Type | Default | Description |
|---|---|---|---|
| `queue` | `str` | `"default"` | Queue name to land on |
| `tries` | `int` | `1` | Max attempts before moving to DLQ |
| `timeout` | `int` | `0` (no limit) | Worker kills the job after this many seconds |
| `backoff` | `int` | `0` (immediate) | Seconds to wait before each retry |
| `retry_until` | `datetime \| None` | `None` | Hard deadline — no more retries after this UTC datetime |

## Dispatching

```python
from arvel.facades import Bus


await Bus.dispatch(SendWelcomeEmail(user_id=42))
```

For deferred dispatch:

```python
await Bus.dispatch(SendWelcomeEmail(user_id=42)).delay(seconds=300)
```

For dispatch within a DB transaction (only enqueue if the transaction commits):

```python
async with DB.transaction():
    user = await User.create(...)
    await Bus.dispatch_after_commit(SendWelcomeEmail(user_id=user.id))
```

## Running workers

```bash
uv run arvel queue:work --queue=emails
```

Flags:

- `--queue=NAME` — the queue to consume (default `default`).
- `--stop-when-empty` — exit when the queue is drained. Useful for cron-driven workers or test runs.

Per-job retry count and timeout are declared on the `Job` class (`tries`, `timeout` — see above). To run multiple queues in priority order, run one worker per queue under your supervisor and order them by priority in your process manager.

For graceful restarts after a deploy, send `SIGTERM` to each worker:

```bash
# systemd
systemctl restart arvel-queue-worker

# kubernetes (rolling restart on the worker Deployment)
kubectl rollout restart deploy/arvel-queue-worker
```

`queue:work` installs a `SIGTERM` handler that finishes the current job before exiting.

## Inspecting queue depth

```bash
uv run arvel queue:size                  # pending count on the default queue
uv run arvel queue:size --queue=emails   # pending count on a named queue
```

`queue:size` queries the underlying driver's `size()` method and prints the result. Use it during incident response, in deployment checks, or from a cron alert to watch for backpressure.

## Retries and DLQ

When a job throws, Arvel:

1. Increments the attempt count.
2. If `attempts < tries` **and** the job's `retry_until` hasn't passed, re-queues after the configured `backoff` delay.
3. Otherwise, moves the job to the **dead-letter queue** (table `failed_jobs`).

Inspect failures:

```bash
uv run arvel queue:failed
```

Retry a single failed job by UUID. The attempt counter resets to `0` so the full `tries` budget is available again:

```bash
uv run arvel queue:retry <job-uuid>
```

Delete a single failed job by UUID:

```bash
uv run arvel queue:forget <job-uuid>
```

Delete all failed jobs:

```bash
uv run arvel queue:flush
```

### Backoff strategy

Set `backoff` on your job class to add a delay between retries:

```python
class ImportOrder(Job):
    order_id: int
    tries = 5
    backoff = 60          # wait 60 s between each retry

    async def handle(self) -> None: ...
```

For a hard deadline instead of a fixed attempt count:

```python
from datetime import UTC, datetime, timedelta


class SyncInventory(Job):
    sku: str
    tries = 99
    retry_until = datetime.now(UTC) + timedelta(hours=2)

    async def handle(self) -> None: ...
```

The worker stops retrying as soon as `retry_until` passes, even if attempts remain.

## Batches and chains

For coordinated job sets, use a **batch** (parallel) or **chain** (sequential):

```python
batch = await (
    Bus
    .batch([
        ImportRow(row_id=1),
        ImportRow(row_id=2),
        ImportRow(row_id=3),
    ])
    .name("nightly-import")
    .on_complete(lambda b: Log.info("batch done", id=b.id))
    .dispatch()
)


chain = await (
    Bus
    .chain([
        ProcessUpload(file_id=42),
        TranscodeVideo(file_id=42),
        NotifyOwner(user_id=alice.id, file_id=42),
    ])
    .dispatch()
)
```

A chain stops on the first failure; a batch records each job's outcome independently.

## Idempotency

Jobs may retry. Always design `handle()` to be idempotent.

```python
class ChargeCard(Job):
    order_id: int
    idempotency_key: str

    async def handle(self) -> None:
        if await Payment.where(idempotency_key=self.idempotency_key).exists():
            return  # already charged
        await stripe_charge(self.order_id, self.idempotency_key)
```

## Testing

Test job handlers directly by instantiating and calling `.handle()` — no queue infrastructure needed:

```python
async def test_send_welcome_email_handler() -> None:
    driver = Mail.fake()
    user = await UserFactory().create()
    await SendWelcomeEmail(user_id=user.id).handle()
    assert len(driver.sent) == 1
    assert driver.sent[0].to == user.email
```

To verify that a job is dispatched during an HTTP request, use the synchronous queue driver and inspect the queue directly, or spy on `Bus.dispatch` with `unittest.mock.patch`.

## Where to next?

- [Events](events.md) — when a `ShouldQueue` listener fans through the queue.
- [Rate Limiting](rate-limiting.md) — same backing store can throttle queue dispatch.
- [Mail](mail.md) — Mailables that opt into queuing.
