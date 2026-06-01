# ADR-098: ShouldQueue Uses ListenerJob Bridging to Bus

**Status**: Accepted | **Date**: 2026-05-18 | **WI**: arvel-009

## Context

`ShouldQueue` listeners should run asynchronously via the existing queue infrastructure (WI-008 Bus). We need to bridge `EventDispatcher` → `Bus` without creating a circular dependency between `arvel.events` and `arvel.queue`.

## Decision

`ListenerJob` is a `Job` subclass in `arvel.events.listener_job` that holds:
- `listener_class_key: str` — `module.ClassName` for `JobRegistry`
- `event_class_key: str` — `module.ClassName` for `EventRegistry`
- `event_json: str` — `event.model_dump_json()`

`EventDispatcher` lazily imports `Bus` facade and calls `Bus.dispatch(ListenerJob(...))`.
`ListenerJob.handle()` uses `EventRegistry` (dict in `arvel.events.event`) to deserialize the event, then looks up the listener class via `JobRegistry` and calls `handle(event)`.

## Rationale

- **No circular import**: `arvel.events.listener_job` imports `arvel.queue.job.Job` (events → queue, not queue → events)
- **JobRegistry allowlist**: listener class names are safe because they must be `Job` subclasses AND must have been imported before the worker starts
- **Graceful fallback**: if `Bus` is not bound (test environments without QueueServiceProvider), `EventDispatcher` falls back to inline execution and logs a DEBUG message
- **EventRegistry**: mirrors `JobRegistry`, populated by `Event.__init_subclass__` — same security guarantees

## Consequences

- `ListenerJob` is registered in `JobRegistry` automatically (it's a `Job` subclass)
- All `ShouldQueue` listener classes must be imported before workers start (same requirement as regular `Job` classes)
- If `Bus` is unavailable, `ShouldQueue` listeners run synchronously — behavior change must be documented
- `EventDispatcher` depends on `arvel.queue` at runtime (not at import time — lazy import inside dispatch method)
