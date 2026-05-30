# ADR-034: Driver selection — four backends with sync as default

**Status**: Accepted
**Date**: 2026-05-18

## Context

The Queue subsystem needs at least one "real" async driver for production and a zero-setup driver for
testing/development. The brainstorm doc and ROADMAP specify four drivers that match Laravel's built-in
queue backends.

## Options

| Option | Pros | Cons |
|---|---|---|
| A: Taskiq only | Single integration, modern async-native | Requires external broker setup even for tests |
| B: Four drivers (sync/database/redis/taskiq) | Matches Laravel parity; zero-setup sync for tests; database for small-scale; redis for single-host; taskiq for scale | More implementation surface |
| C: Two drivers (sync + taskiq) | Smaller scope | Misses database and redis cases that many apps use |

## Decision

**Option B — four drivers**, matching ROADMAP E8 scope. Each driver is behind `QueueConnection`
Protocol; drivers are added/removed without changing the Bus/QueueManager interface.

Default driver is `sync` (zero-setup, great for development and testing). Production setups switch
via `QUEUE_CONNECTION=taskiq` (or redis/database).

## Consequences

- **Gain**: Full Laravel parity; any driver is one env var change away.
- **Accept**: Four driver implementations to test and maintain.
- **Risk**: Taskiq lifecycle management — mitigated by `QueueServiceProvider.boot/shutdown`.
