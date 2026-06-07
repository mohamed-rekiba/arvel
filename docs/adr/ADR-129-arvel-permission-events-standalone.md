# ADR-129 — arvel-permission: Standalone event system

**Status**: Accepted
**Date**: 2026-05-24

## Context

`arvel-permission` mutates state (role assigned, permission revoked, roles
synced, etc.) and downstream callers — audit logs, cache invalidators, ops
dashboards — want to react. The package owns its event surface. Three options:

1. Integrate with Arvel's event dispatcher (requires the `arvel` container at runtime).
2. Standalone pub/sub in `events.py` (no dependency on the container).
3. Callback hook attribute on the mixin.

## Decision

Option 2 — standalone `events.py` with a module-level listener registry. Opt-in via
`PermissionConfig.events_enabled`. The container is accessed lazily only when `events_enabled=True`
and an event fires.

## Consequences

- Positive: Package remains independently testable without the full Arvel container.
- Positive: Zero overhead when `events_enabled=False` (default).
- Negative: Not integrated with Arvel's event queue/replay — listeners are in-process only.
  Acceptable for the current use case (audit logging, cache invalidation).
