# Epic: Default broadcast payload is JSON-safe

## Summary
`ShouldBroadcast.broadcast_with()` built the default payload with a python-mode `model_dump()`, so
`datetime`/`UUID`/`Decimal` fields stayed as Python objects. Every real driver (`RedisBroadcaster`,
`PusherBroadcaster`) `json.dumps`'s the payload, so broadcasting any event with one of those fields
— the common case — failed at send with a `BroadcastDriverError`. The default now uses
`model_dump(mode="json")`, producing JSON-safe values.

**Module:** broadcasting · **Spec:** `docs/pipeline/specs/WI-arvel-012-broadcast-payload-json-safe.md`

## Stories

### Story 1: Events with rich types broadcast successfully
**As an** application developer, **I want** the default broadcast payload to be JSON-safe, **so that**
an event with a `datetime`, `UUID`, or `Decimal` field actually sends instead of raising.

**Acceptance Criteria**:
- [x] Given an event with `datetime`/`UUID`/`Decimal` fields and no `broadcast_with` override, when broadcast, then the payload contains JSON-safe values (ISO string / str / str).
- [x] Given that default payload, when a driver `json.dumps` it, then it serializes without raising.
- [x] Given a plain-typed event (int/str), when broadcast, then the payload is unchanged.

**Security Requirements**:
- [x] None (no change to channel auth or signing).

**Documentation Requirements**:
- [x] `docs/site/docs/features/broadcasting.md` notes the default uses `model_dump(mode="json")` and why.

**Requirement Refs**: SPEC-1, SPEC-2, SPEC-3
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001..011.

## Notes
- The kit doesn't broadcast directly; the defect is reachable through any `Event` + `ShouldBroadcast`
  carrying a timestamp/UUID/Decimal field.
- Deferred follow-ups (separate work items):
  - **Auth presence/private discriminator** — `BroadcastAuthController` keys `channel_data` signing on
    the callback returning a dict instead of the `private-`/`presence-` channel-name prefix.
  - **`toOthers()`** — the event/auto-broadcast path doesn't thread `except_socket_id`.
  - **Pusher driver** — not auto-buildable from `BroadcastConfig`; `body_md5` vs httpx wire-serialization
    signing parity.
