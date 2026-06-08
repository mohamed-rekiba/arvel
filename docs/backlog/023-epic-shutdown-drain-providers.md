# Epic: Application shutdown drains every provider

## Summary
Graceful shutdown must tear down every registered provider even when one of them
raises, so a single failing teardown never strands the providers after it (most
importantly the database provider, which disposes the connection pool). The first
failure is logged and re-raised as `ShutdownError`; the rest still run and the app
is always marked un-booted.

**Module:** application kernel · **Spec:** `docs/pipeline/specs/WI-arvel-023-shutdown-drain-providers.md`

## Stories

### Story 1: One failing provider doesn't strand the others
**As a** developer running an Arvel app, **I want** every provider's `shutdown()`
to run on graceful exit even if one of them throws, **so that** resources like the
DB connection pool are always released and I don't leak connections on each deploy.

**Acceptance Criteria**:
- [ ] Given two providers where the one shut down first (reverse order) raises, when the app shuts down, then the other provider's `shutdown()` still runs.
- [ ] Given a failing provider ahead of `DatabaseServiceProvider` in reverse order, when the app shuts down, then `engine.dispose()` still runs.
- [ ] Given a provider raises during shutdown, when shutdown completes, then `ShutdownError` is raised and its `.provider` is the first failing provider.

**Security Requirements**:
- [ ] None (internal lifecycle contract).

**Documentation Requirements**:
- [ ] None user-facing — behavior is internal to the kernel; covered by spec + docstring.

**Requirement Refs**: C1
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: Shutdown always clears booted state
**As a** developer, **I want** the app marked un-booted after shutdown even when a
provider failed, **so that** a retry doesn't double-tear-down already-stopped
services and providers.

**Acceptance Criteria**:
- [ ] Given a provider raises during shutdown, when shutdown finishes (with `ShutdownError`), then `_booted` is `False`.
- [ ] Given that state, when `shutdown()` is called again, then it is a no-op (no double disconnect/shutdown).

**Requirement Refs**: C2
**Priority**: Must · **Complexity**: Small · **Status**: Done
