# ADR-107: `ShouldBroadcast` is a Mixin on `Event`, Not a Separate Listener Type

**Status**: Accepted
**Date**: 2026-05-18

## Context

Laravel marks broadcasting events by implementing the `ShouldBroadcast` interface. Three Pythonic candidates:

- **A**: Marker mixin (`class OrderShipped(Event, ShouldBroadcast):`). `EventDispatcher` checks `isinstance(event, ShouldBroadcast)`.
- **B**: Separate `BroadcastEvent` base class users inherit from instead of `Event`.
- **C**: Decorator `@broadcastable(channels=["..."])` applied to a regular `Event` subclass.

## Decision

**Option A** — `ShouldBroadcast` is a mixin (alongside the existing `Event` base) with optional override hooks `broadcast_on`, `broadcast_as`, `broadcast_with`. `EventDispatcher.dispatch` checks `isinstance(event, ShouldBroadcast)` and calls `Broadcast.send(event)` after running listeners.

Matches the existing `ShouldQueue` mixin pattern (WI-009 ADR-098), keeps the Laravel mental model 1:1, and composes cleanly with `ShouldQueue` (an event can be both queued AND broadcasted).

## Consequences

- An event mixing in `ShouldBroadcast` without overriding `broadcast_on()` raises `NotImplementedError` at dispatch time. Loud failure, not silent no-op.
- The dispatcher runs listeners FIRST, then broadcasts. Order is deterministic and matches Laravel. Broadcast failures are caught + logged; listeners always run regardless.
- Composition: an event can mix `ShouldBroadcast` AND `ShouldQueue`. The listener runs queued; the broadcast runs synchronously from the original dispatch site. This is intentional — broadcasting is typically faster than queueing a listener job, and delaying user-facing real-time messages defeats the purpose.
- Default `broadcast_with()` returns `model_dump()` for Pydantic-based events (which is all of them post-ADR-102). Users override only when they need to trim or shape the payload.
