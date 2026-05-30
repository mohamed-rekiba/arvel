# ADR-059: `BroadcasterFake` Lives Under `arvel.testing.broadcasting`

**Status**: Accepted
**Date**: 2026-05-18

## Context

`BroadcasterFake` is a test-only `Broadcaster` implementation that records broadcasts in memory for assertion. Where does it live?

- **A**: `arvel.testing.broadcasting.BroadcasterFake` — under a new top-level `arvel.testing` package, anticipating WI-015 Quality which will ship a full `ArvelTestCase` + `Fake*` suite.
- **B**: `arvel.broadcasting.testing.BroadcasterFake` — under the subsystem it tests; easier to import in tests of just that subsystem.
- **C**: Ship it in WI-015 only; WI-013 tests use a hand-rolled stub.

## Decision

**Option A** — `arvel.testing.broadcasting.BroadcasterFake`. WI-013 establishes the `arvel.testing/` directory as a first-class part of the public API surface, with `arvel.testing.broadcasting` as its first occupant. WI-015 will add `arvel.testing.{mail,notifications,events,cache,...}` siblings.

This is consistent with Laravel's `Illuminate\Support\Testing\Fakes\BroadcastFake` namespace: testing utilities are a domain of their own, not a sub-namespace of each production subsystem. It also avoids the awkward pattern of production code optionally importing from `arvel.broadcasting.testing` (a layering smell — production shouldn't import from a `testing/` submodule even at type-check time).

## Consequences

- **Pro**: `arvel.testing` is now a first-class import path. WI-015 grows it without restructuring.
- **Pro**: Mirrors Laravel's mental model exactly.
- **Pro**: Production code under `arvel.broadcasting.*` never imports anything from `arvel.testing.*` — clean layering.
- **Con**: One extra namespace level on every import (`from arvel.testing.broadcasting import BroadcasterFake` vs `from arvel.broadcasting.testing import BroadcasterFake`). Minor.
- `BroadcasterFake.bind()` is an `async @contextmanager` that swaps the bound broadcaster on the container and restores the original on exit. Tests use it via pytest fixture or directly:
  ```python
  async with BroadcasterFake.bind() as fake:
      await Event.dispatch(MyEvent(...))
      fake.assert_broadcasted(MyEvent, on_channels=["..."])
  ```
- The fake records `RecordedBroadcast(event_name, channels, payload, except_socket_id)` immutably. `recorded()` returns a `tuple` so test assertions cannot mutate the record list.
