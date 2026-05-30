# ADR-045: Worker Retry + DLQ — Attempt Tracking in Envelope

**Status**: Accepted
**Date**: 2026-05-18

## Context

`JobEnvelope` is the wire format persisted in queue backends. For retry logic, the number of past attempts must travel with the job across re-enqueue cycles. Two candidates:

- **Option A**: Track attempts in the envelope (top-level field alongside `job_class`/`payload`)
- **Option B**: Track attempts in a separate backend-side counter keyed by job ID

## Decision

**Option A** — `attempts: int = 0` added to `JobEnvelope`.

Rationale:
- Self-contained: no backend-side state or extra round-trips
- Backend-agnostic: works identically on sync, redis, database, taskiq drivers
- Backward compatible: `from_json()` falls back to `0` when the key is absent
- Simple: one field, one source of truth

## Consequences

- `JobEnvelope.to_json()` always emits `"attempts"`
- `Job.to_envelope()` removes `tries` from the exclusion set so max-retry survives serialization
- `Worker` reads `envelope.attempts` and `job.tries` — no new protocol methods required
- Delayed re-enqueue (backoff sleep in the driver) is NOT implemented in this ADR; deferred to a future `push(delay=N)` Protocol extension
