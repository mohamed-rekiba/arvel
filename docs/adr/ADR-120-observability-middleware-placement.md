# ADR-120: ObservabilityMiddleware Placement (Outermost, Before Auth)

**Date:** 2026-05-22
**Status:** Accepted
## Context

`ObservabilityMiddleware` needs to open an OTel span for the full request lifecycle,
propagate `traceparent` headers, and inject `request_id` into the log context.
The auth middleware (`JwtGuard` / `AuthenticateMiddleware`) must run before `user_id`
is known. There is a tension: the middleware must be outermost to measure total
request duration, but `user_id` is only available after auth resolves.

## Decision

Register `ObservabilityMiddleware` as the **outermost middleware** (added first in
the Starlette middleware stack, so it wraps everything else). The middleware
binds `request_id` and `route` before the request begins, then reads
`request.state.user_id` in a post-response hook (after `await call_next(request)`)
to late-bind `user_id` into the span attributes and log context.

This means:
- `request_id`, `route`, `service` are available on all log records in the request.
- `user_id` is present on log records emitted AFTER `call_next` returns (error logs,
  response hooks) but NOT on log records emitted during request processing by the
  route handler itself — unless the handler explicitly calls
  `Log.with_context(user_id=...)`.
- The span's `user_id` attribute is set after the span is active, which is supported
  by the OTel SDK.

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Register ObservabilityMiddleware after auth middleware | User_id available, but span doesn't cover auth time; loses timing accuracy |
| Two middlewares (outer for span/request_id, inner for user_id) | Complexity; user_id still not in handler-time logs |
| Inject user_id via a request lifecycle hook in the auth layer | Couples auth to observability; wrong boundary |

## Consequences

- Handler-time log records won't carry `user_id` unless the app calls
  `Log.with_context(user_id=current_user.id)` in a dependency or handler.
  This is documented as the expected pattern.
- The DX guide recommends a `get_current_user` FastAPI dependency that also calls
  `Log.with_context(user_id=user.id)` so all handler logs carry the user.
- `request_id` and OTel span are fully reliable for all log correlation even without
  `user_id`.
