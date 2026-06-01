# ADR-100 — Per-message delay and priority as first-class `Job` fields

**Status**: Accepted
**Date**: 2026-05-19
**Supersedes**: none
**Superseded by**: none
**Related**: ADR-094 (Job is BaseModel), ADR-096 (Job registry allowlist), ADR-097 (Worker retry/DLQ)

## Context

Before WI-018, `delay` was a driver-specific feature: the `database` driver carried a one-off `push_delayed(envelope, queue, delay_seconds)` method; the `sync`, `redis`, and `taskiq` drivers had no concept of delay. Priority did not exist on any driver.

The brainstorm (`docs/plans/2026-05-19-queue-amqp-and-delay-priority-design.md`) framed three options:

1. **Per-message metadata on `JobEnvelope` only.** App authors set delay/priority by overriding `Bus.dispatch` kwargs every time. Pro: smallest blast radius. Con: discoverability is poor; jobs that "always run with priority 7" duplicate the kwarg everywhere they're dispatched.
2. **Per-Job-class fields, no per-dispatch override.** `class HighPriorityJob(Job): priority = 7` and that's it. Pro: declarative. Con: can't bump priority for one specific instance.
3. **Per-Job-class fields with per-dispatch override.** Both `class HighPriorityJob(Job): priority = 7` AND `bus.dispatch(job, priority=9)` work. Override `None` means "use the field". Pro: covers both cases. Con: more API surface.

## Decision

Option 3.

- `Job.delay: int | timedelta = 0` and `Job.priority: int = Field(0, ge=0, le=9)` are first-class Pydantic fields on the `Job` base class.
- `JobEnvelope` carries `delay: int` (seconds) and `priority: int` after normalisation.
- `Bus.dispatch(job, *, delay=None, priority=None)` overrides the field when non-`None`.
- The `payload` produced by `Job.to_envelope()` excludes `delay`, `priority`, `queue`, and `timeout` — these are envelope metadata, not job state.

## Consequences

### Positive

- **Symmetric API**: same construct works whether you want "this job class always runs with priority 7" or "this one dispatch needs priority 9".
- **Type-safe**: Pydantic field validation (`ge=0, le=9`) means out-of-range values fail at instantiation, not at the broker.
- **Wire-format breaking change is greenfield-safe**: per `no-backward-compatibility.mdc` and no published v1 of `JobEnvelope` exists outside this repo.

### Negative

- **Field shadowing**: A subclass that wanted a `delay: str` field for its own payload reasons can't. Acceptable — payload fields named `delay` or `priority` would be confusing regardless.
- **`Bus.dispatch` grows two kwargs**. Worth it for symmetry; `connection: str | None = None` was already there as a placeholder.

### Neutral

- The retired `DatabaseConnection.push_delayed()` method is deleted (greenfield, no shim).

## Driver matrix

| Driver | Delay implementation | Priority implementation |
|---|---|---|
| `sync` | `await asyncio.sleep(delay)` then `handle()` | No-op (single in-flight) |
| `database` | `available_at` column = `now + delay` | `priority` column; `ORDER BY priority DESC, available_at ASC` |
| `redis` (direct) | `:scheduled` ZSET, score = `available_at_ms` | `:ready` ZSET, score = `-priority` |
| `taskiq` + `redis://` | `taskiq-redis` schedule source | queue-name suffix `:p<N>` (see ADR-101) |
| `taskiq` + `amqp://` | RabbitMQ x-delay header | Native (`max_priority=9` on queue declaration) |

## Worker retry semantics (FR-018-17)

When the worker re-enqueues a failed envelope:

- `envelope.priority` is **preserved** (the job was high-priority on first dispatch; it stays high-priority for retries).
- `envelope.delay` is **reset to 0** (the original delay was consumed on first dispatch; retried jobs are immediately due — they're a continuation, not a re-schedule).

This is the only place in the codebase where retry semantics diverge from "treat the retry exactly like a fresh push" — and it's the correct choice because the alternative (retry inherits the original delay) means a job with `delay=60` that fails on first run waits another 60s before being retried, which is bug-equivalent to halving the retry rate.
