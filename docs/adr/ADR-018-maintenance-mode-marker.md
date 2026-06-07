# ADR-018 — Maintenance mode marker design

**Status**: Accepted
**Date**: 2026-05-19
**Last reconciled**: 2026-06-07 (WI-arvel-005 renumbered ADR-127 → ADR-018)
**Context**: (Console parity tail)
**Related**: SAD-023 §3.2

## Context

`down` and `up` commands need a persistent marker that signals the running ASGI app to switch into maintenance mode. We considered three options:

1. **Cache-based marker** — store the maintenance flag in the cache backend (Redis/memory).
2. **Database-backed flag** — a settings row in a config table.
3. **Filesystem marker** — a file at `storage/framework/down`.

Laravel uses the filesystem approach.

## Decision

Use a **filesystem marker** at `storage/framework/down`. The marker contains JSON with the bypass secret, retry-after, refresh hint, optional template path, and a timestamp:

```json
{
  "secret": "uVoXX...32-char-token",
  "retry": 60,
  "refresh": null,
  "template": null,
  "started_at": "2026-05-20T00:00:00+00:00"
}
```

## Rationale

| Aspect | Filesystem | Cache | Database |
|---|---|---|---|
| Survives cache flushes | ✓ | ✗ | ✓ |
| No external dep | ✓ | ✗ (needs Redis/store running) | ✗ (needs DB up) |
| Works during DB outage | ✓ | depends | ✗ |
| Works during cache outage | ✓ | ✗ | ✓ |
| Multi-host friendly | ✗ (each host needs the marker) | ✓ | ✓ |
| Laravel parity | ✓ | ✗ | ✗ |

**Filesystem wins** because:

1. Maintenance mode often coincides with cache or DB issues — the marker must be readable when those are down.
2. Single-host is the default deployment for the projects this framework targets. Multi-host deployments will deploy maintenance mode via their orchestrator (Kubernetes pre-stop hook, deployment script) — the marker is part of the deployment unit, not runtime state.
3. Laravel parity matters for the developer mental model.

## Consequences

### Positive

- Marker is durable and doesn't depend on cache or DB.
- Inspectable from the shell (`cat storage/framework/down`).
- Simple to ship across deployments.

### Negative

- Multi-host deployments need to broadcast the marker to all hosts. This is an orchestration concern, not a framework concern.
- The middleware does a `path.exists()` call per request. Mitigated by a 1-second TTL in-memory cache.

## Alternatives rejected

- **Redis-backed marker**: tight coupling to the cache backend; breaks when Redis is down (which is exactly when you may need maintenance mode).
- **Database-backed flag**: tight coupling to DB; breaks during DB migrations (which is the most common reason to be in maintenance mode).
- **No marker; only env var**: requires app restart to toggle — defeats the purpose.

## Implementation notes

- Marker path: `storage/framework/down` (gitignored).
- Owned by `MaintenanceModeManager` (`arvel.maintenance.manager`).
- Read by `MaintenanceModeMiddleware` (Starlette middleware) with a 1-second TTL cache.
- `HttpServiceProvider` binds the manager so it's available to any app.
- Middleware is conditionally added in `Application.into_asgi` only when the manager is bound.
