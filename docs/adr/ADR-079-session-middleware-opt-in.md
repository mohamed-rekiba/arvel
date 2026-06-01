# ADR-079 — StartSession middleware is opt-in, not auto-global

**Status**: Accepted
**Date**: 2026-05-17
**Deciders**: Arvel core team

---

## Context

`SessionServiceProvider` could automatically prepend `StartSession` to every request's middleware
stack, or it could register the middleware under a name and let each app opt in.

## Decision

`StartSession` is NOT auto-applied globally. `SessionServiceProvider.register()` binds the
`StartSession` class under the name `"session"` in the middleware registry.

Apps enable it per group:

```python
Application.configure(...)
    .with_middleware(lambda mw: mw.group("web", ["session", "csrf"]))
```

## Rationale

1. **API-only apps**: apps that build pure JSON APIs (no browser, no cookies) should not pay the
   session read/write overhead on every request. Auto-global would force them to disable it
   explicitly — the wrong default.
2. **Laravel parity**: Laravel's `StartSession` middleware is in the `web` group, not `global`.
   Apps must explicitly add routes to the `web` group. Arvel mirrors this.
3. **Performance**: session read/write is I/O. Opt-in keeps the critical path (API routes) lean.
4. **Consistency with throttle**: `Throttle` middleware (WI-002) is also opt-in via group.

## Consequences

- Apps that forget to add `"session"` to their middleware group will find `request.state.session`
  absent. The error message from accessing it should be clear: "Session not started — add the
  'session' middleware to your route group."
- The skeleton's `routes/web.py` will include a comment showing how to enable sessions.
