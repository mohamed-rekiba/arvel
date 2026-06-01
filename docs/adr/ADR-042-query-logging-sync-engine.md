# ADR-042 — QueryLoggingServiceProvider hooks sync_engine events

**Status**: Accepted
**Date**: 2026-05-18

## Context

SQLAlchemy's `AsyncEngine` wraps a synchronous `Engine`. The event system (`event.listens_for`)
attaches to the synchronous layer. Two options for the attachment point: (a) `AsyncEngine` directly,
or (b) `AsyncEngine.sync_engine`.

## Decision

Attach to `engine.sync_engine`:

```python
engine: AsyncEngine = container.make(AsyncEngine)
_attach_logging(engine.sync_engine, slow_ms=...)
```

## Rationale

- SQLAlchemy's `before_cursor_execute` and `after_cursor_execute` events are synchronous events on the synchronous cursor — they fire regardless of the async wrapper.
- `AsyncEngine` does not expose the event interface directly for cursor-level hooks.
- `engine.sync_engine` is the canonical attachment point per SQLAlchemy documentation for `AsyncEngine` users wanting cursor-level events.

## Alternatives Rejected

- **Hook `AsyncEngine` directly**: The async engine does not expose `before_cursor_execute` / `after_cursor_execute`. Attaching would silently no-op.
