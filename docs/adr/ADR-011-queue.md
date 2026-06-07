# ADR-011 — Queue Subsystem

**Status**: Accepted
**Date**: original decisions 2026-05-18 – 2026-05-19; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: Job as Pydantic BaseModel, four-driver matrix, job-class allowlist, worker loop design, ShouldQueue / Bus integration, worker retry / DLQ, first-class delay & priority, broker selection by URL scheme.

## Why this is one ADR

The queue subsystem is one piece of code — drivers, broker, worker, retry, allowlist, ShouldQueue. The eight ADRs describe its joints; together they explain how Arvel runs background work.

---

## § 1 — Job model — Pydantic BaseModel as the job primitive

**Originally**: ADR-094 · Date: 2026-05-18

### Context

We need a typed, serializable unit of work. The wire format must support Pydantic validation on
deserialization (prevents invalid payloads from crashing the worker). Laravel uses PHP Serializable /
JSON — we need the Python equivalent that fits our strict-typing posture.

### Options

| Option | Pros | Cons |
|---|---|---|
| A: Pydantic BaseModel | Type-safe, validates on deserialize, model_dump/model_validate built-in, mypy/pyright-friendly | Slightly more ceremony than a plain dataclass |
| B: dataclass + manual JSON | Lighter weight | No validation on deserialize; not mypy-strict without extra work |
| C: msgspec Struct | Faster | Less ecosystem familiarity; no model_validate equivalent |

### Decision

Use **Option A — Pydantic BaseModel**. Consistent with every other typed Arvel primitive (FormRequest,
ArvelSettings, etc.). Validates payload on the worker side before `handle()` — malformed payloads fail
cleanly into `FailedJob` rather than crashing the worker.

Wire format: `JobEnvelope` dataclass with `job_class` (dotted path) + `payload` (model_dump output)
serialized as a single JSON string.

### Consequences

- **Gain**: Type-safe jobs; automatic payload validation; framework consistency.
- **Accept**: Jobs must be Pydantic models (slight constraint on job definition style).
- **Risk**: Deeply nested payload types need Pydantic model wrappers — mitigated by convention.

---

## § 2 — Driver selection — four backends with sync as default

**Originally**: ADR-095 · Date: 2026-05-18

### Context

The Queue subsystem needs at least one "real" async driver for production and a zero-setup driver for
testing/development. The brainstorm doc and ROADMAP specify four drivers that match Laravel's built-in
queue backends.

### Options

| Option | Pros | Cons |
|---|---|---|
| A: Taskiq only | Single integration, modern async-native | Requires external broker setup even for tests |
| B: Four drivers (sync/database/redis/taskiq) | Matches Laravel parity; zero-setup sync for tests; database for small-scale; redis for single-host; taskiq for scale | More implementation surface |
| C: Two drivers (sync + taskiq) | Smaller scope | Misses database and redis cases that many apps use |

### Decision

**Option B — four drivers**, matching ROADMAP E8 scope. Each driver is behind `QueueConnection`
Protocol; drivers are added/removed without changing the Bus/QueueManager interface.

Default driver is `sync` (zero-setup, great for development and testing). Production setups switch
via `QUEUE_CONNECTION=taskiq` (or redis/database).

### Consequences

- **Gain**: Full Laravel parity; any driver is one env var change away.
- **Accept**: Four driver implementations to test and maintain.
- **Risk**: Taskiq lifecycle management — mitigated by `QueueServiceProvider.boot/shutdown`.

---

## § 3 — Job class allowlist for deserialization safety

**Originally**: ADR-096 · Date: 2026-05-18

### Context

Job deserialization requires mapping a string (`job_class: "app.jobs.send_welcome.SendWelcomeEmail"`)
back to a Python class. A naive `importlib.import_module(module) + getattr(class_name)` on an
untrusted string is an OWASP A05 (Injection) vector — an attacker who can write to the queue could
instantiate arbitrary classes.

### Options

| Option | Pros | Cons |
|---|---|---|
| A: Allowlist registry (import-time) | Strong security guarantee; mypy/pyright can see registered types | Requires jobs to be imported by the application at startup |
| B: Dynamic importlib.import_module | Zero registration ceremony | Arbitrary class instantiation from attacker-controlled strings |
| C: pickle | Compact | pickle is a known arbitrary code execution vector — forbidden |

### Decision

**Option A — allowlist registry**. A `JobRegistry` (dict `str → type[Job]`) is populated at import
time when job modules are imported (similar to how Django's app registry works). The worker looks up
`envelope.job_class` in the registry; unknown classes produce a `FailedJob` row with
`error: "Unknown job class"` — they never execute.

Registration is automatic: any `Job` subclass triggers `__init_subclass__` to add itself to the
registry. App code just imports the job class (or the module containing it) before the worker starts.

### Consequences

- **Gain**: Prevents deserialization-based code injection (OWASP A05).
- **Accept**: All job classes must be imported before the worker dispatches them. `bootstrap/providers.py`
  or an explicit import in `bootstrap/app.py` covers this.
- **Risk**: Registry grows unbounded in long-lived processes — mitigated by the fact that job classes
  are small Python objects and there are typically few of them.

---

## § 4 — queue:work worker loop design (asyncio + SIGTERM drain)

**Originally**: ADR-097 · Date: 2026-05-18

### Context

The `queue:work` command needs to run as a long-lived process, poll or block on the queue, and exit
cleanly when asked to stop (e.g., container orchestration sends SIGTERM before shutdown).

### Options

| Option | Pros | Cons |
|---|---|---|
| A: asyncio loop + signal handler (drain) | Native asyncio; clean SIGTERM drain; single codebase path | Slightly more complex signal setup |
| B: Taskiq's built-in worker command | Zero code for Taskiq driver | Only works for Taskiq — database/redis/sync drivers can't use it |
| C: threading.Thread + queue.Queue | Simpler | Blocks GIL; not async-native; incompatible with async handle() |

### Decision

**Option A — single asyncio loop per driver**, with a `_stop` `asyncio.Event` set on `SIGTERM`.

Loop:
```
while not _stop.is_set():
    envelope = await driver.pop_blocking(queue, timeout=sleep_interval)
    if envelope:
        await _process(envelope)
    # else: poll interval elapsed, check stop flag
```

On `SIGTERM`: set `_stop`, let the current job finish, then exit. The `timeout` on `pop_blocking`
(default 3s) ensures the stop event is checked at least every 3 seconds even on blocking drivers.

For the `taskiq` driver: `queue:work` starts Taskiq's broker and delegates to Taskiq's own async
task reception mechanism, but still wraps it in the same SIGTERM-aware loop.

### Consequences

- **Gain**: Works for all four drivers with one code path; clean shutdown guaranteed.
- **Accept**: poll interval adds up-to-3s latency on shutdown. Acceptable for worker processes.
- **Risk**: Very long-running jobs delay shutdown beyond SIGTERM — mitigated by `job.timeout`.

---

## § 5 — ShouldQueue Uses ListenerJob Bridging to Bus

**Originally**: ADR-098 · Status: Accepted | **Date**: 2026-05-18 | **WI**: arvel-009

### Context

`ShouldQueue` listeners should run asynchronously via the existing queue infrastructure (WI-008 Bus). We need to bridge `EventDispatcher` → `Bus` without creating a circular dependency between `arvel.events` and `arvel.queue`.

### Decision

`ListenerJob` is a `Job` subclass in `arvel.events.listener_job` that holds:
- `listener_class_key: str` — `module.ClassName` for `JobRegistry`
- `event_class_key: str` — `module.ClassName` for `EventRegistry`
- `event_json: str` — `event.model_dump_json()`

`EventDispatcher` lazily imports `Bus` facade and calls `Bus.dispatch(ListenerJob(...))`.
`ListenerJob.handle()` uses `EventRegistry` (dict in `arvel.events.event`) to deserialize the event, then looks up the listener class via `JobRegistry` and calls `handle(event)`.

### Rationale

- **No circular import**: `arvel.events.listener_job` imports `arvel.queue.job.Job` (events → queue, not queue → events)
- **JobRegistry allowlist**: listener class names are safe because they must be `Job` subclasses AND must have been imported before the worker starts
- **Graceful fallback**: if `Bus` is not bound (test environments without QueueServiceProvider), `EventDispatcher` falls back to inline execution and logs a DEBUG message
- **EventRegistry**: mirrors `JobRegistry`, populated by `Event.__init_subclass__` — same security guarantees

### Consequences

- `ListenerJob` is registered in `JobRegistry` automatically (it's a `Job` subclass)
- All `ShouldQueue` listener classes must be imported before workers start (same requirement as regular `Job` classes)
- If `Bus` is unavailable, `ShouldQueue` listeners run synchronously — behavior change must be documented
- `EventDispatcher` depends on `arvel.queue` at runtime (not at import time — lazy import inside dispatch method)

---

## § 6 — Worker Retry + DLQ — Attempt Tracking in Envelope

**Originally**: ADR-099 · Date: 2026-05-18

### Context

`JobEnvelope` is the wire format persisted in queue backends. For retry logic, the number of past attempts must travel with the job across re-enqueue cycles. Two candidates:

- **Option A**: Track attempts in the envelope (top-level field alongside `job_class`/`payload`)
- **Option B**: Track attempts in a separate backend-side counter keyed by job ID

### Decision

**Option A** — `attempts: int = 0` added to `JobEnvelope`.

Rationale:
- Self-contained: no backend-side state or extra round-trips
- Backend-agnostic: works identically on sync, redis, database, taskiq drivers
- Backward compatible: `from_json()` falls back to `0` when the key is absent
- Simple: one field, one source of truth

### Consequences

- `JobEnvelope.to_json()` always emits `"attempts"`
- `Job.to_envelope()` removes `tries` from the exclusion set so max-retry survives serialization
- `Worker` reads `envelope.attempts` and `job.tries` — no new protocol methods required
- Delayed re-enqueue (backoff sleep in the driver) is NOT implemented in this ADR; deferred to a future `push(delay=N)` Protocol extension

---

## § 7 — Per-message delay and priority as first-class `Job` fields

**Originally**: ADR-100 · Date: 2026-05-19

### Context

Before WI-018, `delay` was a driver-specific feature: the `database` driver carried a one-off `push_delayed(envelope, queue, delay_seconds)` method; the `sync`, `redis`, and `taskiq` drivers had no concept of delay. Priority did not exist on any driver.

1. **Per-message metadata on `JobEnvelope` only.** App authors set delay/priority by overriding `Bus.dispatch` kwargs every time. Pro: smallest blast radius. Con: discoverability is poor; jobs that "always run with priority 7" duplicate the kwarg everywhere they're dispatched.
2. **Per-Job-class fields, no per-dispatch override.** `class HighPriorityJob(Job): priority = 7` and that's it. Pro: declarative. Con: can't bump priority for one specific instance.
3. **Per-Job-class fields with per-dispatch override.** Both `class HighPriorityJob(Job): priority = 7` AND `bus.dispatch(job, priority=9)` work. Override `None` means "use the field". Pro: covers both cases. Con: more API surface.

### Decision

Option 3.

- `Job.delay: int | timedelta = 0` and `Job.priority: int = Field(0, ge=0, le=9)` are first-class Pydantic fields on the `Job` base class.
- `JobEnvelope` carries `delay: int` (seconds) and `priority: int` after normalisation.
- `Bus.dispatch(job, *, delay=None, priority=None)` overrides the field when non-`None`.
- The `payload` produced by `Job.to_envelope()` excludes `delay`, `priority`, `queue`, and `timeout` — these are envelope metadata, not job state.

### Consequences

#### Positive

- **Symmetric API**: same construct works whether you want "this job class always runs with priority 7" or "this one dispatch needs priority 9".
- **Type-safe**: Pydantic field validation (`ge=0, le=9`) means out-of-range values fail at instantiation, not at the broker.
- **Wire-format breaking change is greenfield-safe**: per `no-backward-compatibility.mdc` and no published v1 of `JobEnvelope` exists outside this repo.

#### Negative

- **Field shadowing**: A subclass that wanted a `delay: str` field for its own payload reasons can't. Acceptable — payload fields named `delay` or `priority` would be confusing regardless.
- **`Bus.dispatch` grows two kwargs**. Worth it for symmetry; `connection: str | None = None` was already there as a placeholder.

#### Neutral

- The retired `DatabaseConnection.push_delayed()` method is deleted (greenfield, no shim).

### Driver matrix

| Driver | Delay implementation | Priority implementation |
|---|---|---|
| `sync` | `await asyncio.sleep(delay)` then `handle()` | No-op (single in-flight) |
| `database` | `available_at` column = `now + delay` | `priority` column; `ORDER BY priority DESC, available_at ASC` |
| `redis` (direct) | `:scheduled` ZSET, score = `available_at_ms` | `:ready` ZSET, score = `-priority` |
| `taskiq` + `redis://` | `taskiq-redis` schedule source | queue-name suffix `:p<N>` (see ADR-011 § 8) |
| `taskiq` + `amqp://` | RabbitMQ x-delay header | Native (`max_priority=9` on queue declaration) |

### Worker retry semantics (FR-018-17)

When the worker re-enqueues a failed envelope:

- `envelope.priority` is **preserved** (the job was high-priority on first dispatch; it stays high-priority for retries).
- `envelope.delay` is **reset to 0** (the original delay was consumed on first dispatch; retried jobs are immediately due — they're a continuation, not a re-schedule).

This is the only place in the codebase where retry semantics diverge from "treat the retry exactly like a fresh push" — and it's the correct choice because the alternative (retry inherits the original delay) means a job with `delay=60` that fails on first run waits another 60s before being retried, which is bug-equivalent to halving the retry rate.

---

## § 8 — Taskiq broker selection by URL scheme; queue-name suffix for Redis-broker priority

**Originally**: ADR-101 · Date: 2026-05-19

### Context

The `taskiq` driver was hard-coded to `taskiq_redis.ListQueueBroker`. To unlock RabbitMQ as a broker — and the native priority + per-message delay it ships — the driver needs a way to choose between brokers.

Three options were considered:

1. **A new config field** (`TaskiqQueueConfig.broker_type: Literal["redis", "amqp"]`). Pro: explicit. Con: redundant with the URL, which already encodes the broker by scheme; two sources of truth invite drift.
2. **A new driver per broker** (`QueueDriver.TASKIQ_AMQP`). Pro: no URL parsing. Con: explodes the driver enum and `_make_connection` factory; "which driver" is now two questions instead of one.
3. **URL-scheme autodetection inside `TaskiqConnection`.** Pro: one source of truth (the URL); same `QueueDriver.TASKIQ` regardless of broker. Con: a tiny `urlparse` + dict-lookup helper that has to know the supported schemes.

### Decision

Option 3.

```python
_BROKER_BY_SCHEME: Final[dict[str, tuple[str, str]]] = {
    "redis":  ("taskiq_redis",    "queue-redis"),
    "rediss": ("taskiq_redis",    "queue-redis"),
    "unix":   ("taskiq_redis",    "queue-redis"),
    "amqp":   ("taskiq_aio_pika", "queue-amqp"),
    "amqps":  ("taskiq_aio_pika", "queue-amqp"),
}
```

Unknown schemes raise `ValueError("Unsupported queue broker scheme: 'X'.")`. Missing modules for known schemes raise `ImportError("arvel requires 'taskiq-{redis,aio-pika}'. Install with: pip install arvel[queue-{redis,amqp}]")`.

### Priority strategy for `redis://` broker

`taskiq-redis`'s `ListQueueBroker` is a single Redis list — no native priority. Three options were considered for honouring `Job.priority` on this path:

1. **Drop priority silently** for `redis://`. Pro: simplest. Con: silently breaks the contract that "priority is honoured by every driver".
2. **Multiple lists, one per priority level.** Pro: faithful. Con: the consumer side (`taskiq-redis`'s worker) doesn't understand "drain p9 before p0 before p3"; we'd have to fork it.
3. **Queue-name suffix `:p<N>`.** Push `priority=7` to `<queue_name>:p7`, `priority=3` to `<queue_name>:p3`. Operators run separate `taskiq worker --queues <queue>:p9,<queue>:p8,...` invocations to drain in priority order.

### Decision

Option 3, with the limitation documented prominently in `docs/pages/queues.md` and `DXD-018`.

### Consequences

#### Positive

- **One source of truth for the broker choice**: the URL. No drift between `broker_url` and a separate `broker_type` field.
- **Native priority on AMQP**: `AioPikaBroker(url=..., max_priority=9)` declares the queue with `max-priority=9` and RabbitMQ does the rest. Operator does nothing extra.
- **`ImportError` is per-broker**: a contributor running `pip install arvel[queue-redis]` and then setting `broker_url=amqp://...` gets a clear message that mentions `queue-amqp`, not `queue-redis`.

#### Negative

- **Redis-broker priority requires operator action.** Running a single `taskiq worker` against the base queue name will NOT see priority-suffixed lists. Operators must enumerate them explicitly: `taskiq worker arvel:p9 arvel:p8 ... arvel:p0`. ADR documents this; DXD-018 + queue docs reinforce. (Rationale: anything more elegant requires forking `taskiq-redis`'s worker, which is out of scope.)
- **`unix://` scheme is mapped to `taskiq-redis`** — which is correct (`taskiq-redis` accepts unix sockets) but slightly surprising. Docstring on `_select_broker_module` explains.

#### Neutral

- The dead `TaskiqQueueConfig.result_backend_url` field is removed (greenfield; no arvel API consumes results today).
- `taskiq-aio-pika` is added as an optional dependency under the new `queue-amqp` extra. Per `105-engineering-preferences.mdc` the version is web-searched at implementation time, not from training data.

### Limitations explicit in code

The redis-broker priority limitation is named in three places so it can't be missed:

1. `arvel/queue/drivers/taskiq_.py` — a comment block on `_route_for_priority` explaining the suffix scheme and why.
2. `docs/dx/DXD-018-queue-amqp-priority.md` §2.4 — per-driver priority semantics table.
3. `docs/pages/queues.md` — operator-facing note (added at Stage 8).

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-094 | 2026-05-18 | Job model — Pydantic BaseModel as the job primitive | § 1 |
| ADR-095 | 2026-05-18 | Driver selection — four backends with sync as default | § 2 |
| ADR-096 | 2026-05-18 | Job class allowlist for deserialization safety | § 3 |
| ADR-097 | 2026-05-18 | queue:work worker loop design (asyncio + SIGTERM drain) | § 4 |
| ADR-098 | — | ShouldQueue Uses ListenerJob Bridging to Bus | § 5 |
| ADR-099 | 2026-05-18 | Worker Retry + DLQ — Attempt Tracking in Envelope | § 6 |
| ADR-100 | 2026-05-19 | Per-message delay and priority as first-class `Job` fields | § 7 |
| ADR-101 | 2026-05-19 | Taskiq broker selection by URL scheme; queue-name suffix for Redis-broker priority | § 8 |
