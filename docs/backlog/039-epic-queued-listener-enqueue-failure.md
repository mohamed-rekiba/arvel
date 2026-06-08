# Epic: Queued listeners must not silently run inline when the broker fails

## Summary
The event dispatcher swallowed every queued-listener enqueue failure and ran the listener
inline. When a queue was configured but the broker was down, the failure vanished (no log)
and a `ShouldQueue` listener ran synchronously in the publish path — blocking it and risking
double execution. Log the failure instead; only run inline when no queue is configured.

**Module:** events · **Spec:** `docs/pipeline/specs/WI-arvel-039-queued-listener-enqueue-failure.md`

## Stories

### Story 1: Broker failures are visible, not swallowed
**As an** operator, **I want** a queued-listener enqueue failure to be logged, **so that**
a broker outage isn't hidden behind a silent inline fallback.

**Acceptance Criteria**:
- [ ] Given a queue is configured, when `Bus.dispatch` raises, then `queued_listener_enqueue_failed` is logged with the listener and event type.
- [ ] Given the enqueue fails, when dispatch continues, then the publish loop does not raise and other listeners still run.

### Story 2: A queued listener is never silently run inline when a queue exists
**As a** developer marking a listener `ShouldQueue`, **I want** it to only run on the queue,
**so that** a transient broker error doesn't run it synchronously (blocking the request,
possibly twice).

**Acceptance Criteria**:
- [ ] Given a queue is configured, when the event dispatches, then the listener is enqueued and not run inline.
- [ ] Given no queue is configured, when the event dispatches, then the listener runs inline (dev fallback) — unchanged.

**Security Requirements**:
- [ ] `ListenerJob` deserialization stays allowlist-only (`ListenerRegistry`/`EventRegistry`); no arbitrary import (A08).

**Requirement Refs**: SPEC-1
**Priority**: Should · **Complexity**: Small · **Status**: Done

## Dependencies
- Builds on WI-009 (allowlist deserialization) — this closes its deferred "Bus-error log-swallow".

## Notes
- Deferred parity-additive items: wildcard/`subscribe()` listeners, event-inheritance dispatch,
  listener return-value halting.
