# ADR-073 — Queue restart marker via cache

**Status**: Accepted
**Date**: 2026-05-19
**Context**: (Console parity tail)
**Related**: SAD-023 §3.3

## Context

`queue:restart` needs to signal all running workers to exit gracefully so the next supervisor (systemd, supervisord, k8s) restarts them with the latest code. The signal must:

- Reach workers running in separate processes.
- Be cheap to poll (workers check it every loop iteration).
- Be cleared automatically when workers restart.

Laravel uses a Redis/cache key (`illuminate:queue:restart`) with a timestamp. Workers compare it to their own `started_at`.

## Decision

Use a **cache-key marker** at `arvel:queue:restart` holding the most recent restart timestamp (ISO 8601 UTC). Workers compare the marker against their own `started_at` once per loop iteration; if the marker is newer, they exit.

## Rationale

| Aspect | Cache key | File marker | Signal (SIGUSR1) |
|---|---|---|---|
| Cross-process | ✓ | ✓ | ✗ (needs PID list) |
| Per-worker scope | ✓ (timestamp comparison) | ✗ (no per-worker state) | ✓ |
| Survives DB outage | ✓ | ✓ | ✓ |
| Cheap to poll | ✓ (cache get) | ✓ (stat) | ✓ (no poll needed) |
| Multi-host | ✓ (shared Redis) | ✗ | ✗ |
| Auto-clears | timestamp-based | manual cleanup | event-based |

**Cache wins** because:

1. Queue workers already require a cache binding (rate-limit store, idempotency).
2. The timestamp comparison is idempotent — workers started after the marker simply ignore it. No cleanup logic needed.
3. Multi-host queue clusters can share a cache key without each worker needing local-filesystem coordination.

## Consequences

### Positive

- Workers respond within one loop iteration (~1 second worst case).
- Same mechanism works in multi-host deployments.
- Idempotent: a stale marker doesn't trigger repeated restarts; workers compare against their own start time.

### Negative

- Requires a cache binding (acceptable — already required for other queue features).
- Marker persists indefinitely. This is fine: comparison is against `started_at`, so it never causes ghost-restarts.

## Alternatives rejected

- **File marker**: doesn't work cross-host in clustered queues.
- **SIGUSR1 signal**: requires the CLI to know every worker's PID. Workers in containers or supervisor-managed environments don't expose their PIDs in a discoverable way.
- **REST API / RPC**: introduces a new endpoint and authentication concern for an internal-only signal.

## Implementation notes

- Cache key: `arvel:queue:restart` (literal string; per-project prefix not needed).
- Value: ISO 8601 timestamp in UTC.
- Owner: `arvel.queue.restart.QueueRestartSignal`.
- Polled by: `Worker.run_until()` once per iteration.
- Comparison: `marker_timestamp > worker.started_at` → set stop event and exit.
