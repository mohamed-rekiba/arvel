# ADR-101 — Taskiq broker selection by URL scheme; queue-name suffix for Redis-broker priority

**Status**: Accepted
**Date**: 2026-05-19
**Supersedes**: none
**Superseded by**: none
**Related**: ADR-100 (Job.delay/Job.priority first-class)

## Context

The `taskiq` driver was hard-coded to `taskiq_redis.ListQueueBroker`. To unlock RabbitMQ as a broker — and the native priority + per-message delay it ships — the driver needs a way to choose between brokers.

Three options were considered:

1. **A new config field** (`TaskiqQueueConfig.broker_type: Literal["redis", "amqp"]`). Pro: explicit. Con: redundant with the URL, which already encodes the broker by scheme; two sources of truth invite drift.
2. **A new driver per broker** (`QueueDriver.TASKIQ_AMQP`). Pro: no URL parsing. Con: explodes the driver enum and `_make_connection` factory; "which driver" is now two questions instead of one.
3. **URL-scheme autodetection inside `TaskiqConnection`.** Pro: one source of truth (the URL); same `QueueDriver.TASKIQ` regardless of broker. Con: a tiny `urlparse` + dict-lookup helper that has to know the supported schemes.

## Decision

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

## Priority strategy for `redis://` broker

`taskiq-redis`'s `ListQueueBroker` is a single Redis list — no native priority. Three options were considered for honouring `Job.priority` on this path:

1. **Drop priority silently** for `redis://`. Pro: simplest. Con: silently breaks the contract that "priority is honoured by every driver".
2. **Multiple lists, one per priority level.** Pro: faithful. Con: the consumer side (`taskiq-redis`'s worker) doesn't understand "drain p9 before p0 before p3"; we'd have to fork it.
3. **Queue-name suffix `:p<N>`.** Push `priority=7` to `<queue_name>:p7`, `priority=3` to `<queue_name>:p3`. Operators run separate `taskiq worker --queues <queue>:p9,<queue>:p8,...` invocations to drain in priority order.

## Decision

Option 3, with the limitation documented prominently in `docs/pages/queues.md` and `DXD-018`.

## Consequences

### Positive

- **One source of truth for the broker choice**: the URL. No drift between `broker_url` and a separate `broker_type` field.
- **Native priority on AMQP**: `AioPikaBroker(url=..., max_priority=9)` declares the queue with `max-priority=9` and RabbitMQ does the rest. Operator does nothing extra.
- **`ImportError` is per-broker**: a contributor running `pip install arvel[queue-redis]` and then setting `broker_url=amqp://...` gets a clear message that mentions `queue-amqp`, not `queue-redis`.

### Negative

- **Redis-broker priority requires operator action.** Running a single `taskiq worker` against the base queue name will NOT see priority-suffixed lists. Operators must enumerate them explicitly: `taskiq worker arvel:p9 arvel:p8 ... arvel:p0`. ADR documents this; DXD-018 + queue docs reinforce. (Rationale: anything more elegant requires forking `taskiq-redis`'s worker, which is out of scope.)
- **`unix://` scheme is mapped to `taskiq-redis`** — which is correct (`taskiq-redis` accepts unix sockets) but slightly surprising. Docstring on `_select_broker_module` explains.

### Neutral

- The dead `TaskiqQueueConfig.result_backend_url` field is removed (greenfield; no arvel API consumes results today).
- `taskiq-aio-pika` is added as an optional dependency under the new `queue-amqp` extra. Per `105-engineering-preferences.mdc` the version is web-searched at implementation time, not from training data.

## Limitations explicit in code

The redis-broker priority limitation is named in three places so it can't be missed:

1. `arvel/queue/drivers/taskiq_.py` — a comment block on `_route_for_priority` explaining the suffix scheme and why.
2. `docs/dx/DXD-018-queue-amqp-priority.md` §2.4 — per-driver priority semantics table.
3. `docs/pages/queues.md` — operator-facing note (added at Stage 8).
