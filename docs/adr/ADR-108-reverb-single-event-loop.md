# ADR-108: Reverb is Single-Event-Loop + Redis Pub/Sub Horizontal Scale

**Status**: Accepted
**Date**: 2026-05-18

## Context

How to scale the Reverb WS server across CPU cores and hosts? Three candidates:

- **A**: Single asyncio event loop per process; scale horizontally by running N processes that share a Redis Pub/Sub channel.
- **B**: Multi-process within one host via `multiprocessing` + IPC for cross-process subscription state.
- **C**: Single process, multiple event loops via thread-per-loop with a coordinator.

## Decision

**Option A** — One process equals one asyncio event loop. Subscriptions are tracked per-process in memory. Cross-process fan-out is via Redis Pub/Sub (the `RedisBroadcaster` PUBLISHes; every reverb process PSUBSCRIBEs to `arvel.broadcasting.*` and forwards matching messages to its locally connected sockets).

Matches Laravel Reverb's design (Reverb runs single-threaded ReactPHP; horizontal scale is process-level). Matches `arvel queue:work` worker design (one worker per process, scale via process count). Doesn't add a new operational concept.

## Consequences

- **Pro**: Operationally simple. `systemd` units, supervisor configs, Kubernetes Deployments all work without ceremony.
- **Pro**: Zero cross-process IPC complexity. Redis is already a hard dependency for the framework's queue, cache, session paths.
- **Pro**: Each process is independent; killing one doesn't affect others. Rolling deploys with drain-then-replace work cleanly.
- **Con**: Bound by the single event loop's throughput. Per NFR-013-004, we target ≥ 1000 concurrent connections per process at < 5 % CPU each (steady-state idle). High-write-throughput channels with thousands of subscribers per channel will eventually saturate a single loop — at which point operators add more processes.
- **Con**: A subscriber on process A won't receive `except_socket_id=X` exclusions for an event broadcast on process B unless we include `socket_id` in the Redis envelope. We do. The connection that originated the broadcast knows its own `socket_id` from `pusher:connection_established` and passes it via the auth controller / HTTP context.
- Presence-channel member rosters are per-process. A user on process A is NOT visible in the roster sent to a new subscriber on process B. Documented limitation for v1; cross-process presence sync deferred to WI-016 hardening if user demand surfaces.
