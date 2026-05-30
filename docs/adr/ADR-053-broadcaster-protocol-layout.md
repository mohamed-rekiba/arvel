# ADR-053: `Broadcaster` Protocol + Driver Layout

**Status**: Accepted
**Date**: 2026-05-18

## Context

The broadcasting subsystem needs a stable driver contract. Four shipped drivers (`log`, `null`, `redis-pubsub`, `pusher`) plus user-defined drivers must all conform. Three candidates:

- **A**: Inheritance — `class Broadcaster(ABC)` with `@abstractmethod async def broadcast(...)`.
- **B**: `typing.Protocol` with `@runtime_checkable` — structural typing, no ABC.
- **C**: Concrete class with a callback registry — closures pretending to be drivers.

## Decision

**Option B** — `Broadcaster` is a `@runtime_checkable` `typing.Protocol`. Drivers live at `arvel.broadcasting.drivers.{log_,null_,redis_,pusher_}.py`. `BroadcastManager.driver(name)` is the single resolver.

Layout mirrors `arvel.cache.manager.CacheManager` / `arvel.session.manager.SessionManager` / `arvel.storage.manager.StorageManager` — established framework pattern (WI-006). Familiar, type-safe, and zero-friction for users adding their own driver.

## Consequences

- User-defined drivers do NOT need to import `arvel.broadcasting.Broadcaster` to inherit from it; structural typing matches by shape.
- `isinstance(driver, Broadcaster)` works at runtime for tests and assertions.
- The driver constructor signature is each driver's concern — `_resolve(name)` in the manager owns construction-time wiring (lazy imports for the optional `redis` and `httpx` deps).
- Driver filenames end in `_` (e.g., `log_.py`) to avoid shadowing Python's `logging` module.
