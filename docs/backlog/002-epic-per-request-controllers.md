# Epic: Controllers resolve fresh per request

## Summary
Controller actions must run on a fresh instance per HTTP request, like Laravel, so
per-request state on `self` never bleeds across requests or races between concurrent
requests. Constructor dependencies keep their declared lifetimes (singletons stay
shared); only the controller shell is new each request.

**Module:** routing / http · **Spec:** `docs/pipeline/specs/WI-arvel-002-per-request-controllers.md`

## Stories

### Story 1: Fresh controller per request
**As a** developer writing controllers, **I want** a new controller instance per
request, **so that** state I set on `self` during one request never leaks into the
next request or another user's concurrent request.

**Acceptance Criteria**:
- [x] Given a method controller that mutates `self` state, when I send it N requests, then each request sees only its own state (no accumulation across requests).
- [x] Given an invokable (`__call__`) controller, when I send it N requests, then it behaves identically — a fresh instance per request.
- [x] Given a controller with constructor dependencies registered as `singleton()`, when it serves multiple requests, then the dependency instance is shared while the controller itself is new each time.

**Security Requirements**:
- [x] No cross-request / cross-user state bleed (a per-request cache of the authenticated user on `self` cannot leak to another request).

**Documentation Requirements**:
- [x] `docs/site/docs/the-basics/controllers.md` states controllers resolve fresh per request (corrected from the previous "created at boot" note).

**Requirement Refs**: SPEC-1, SPEC-2, SPEC-4
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: DI misconfiguration still fails at boot
**As an** operator, **I want** an unresolvable controller dependency to fail when the
app starts, **so that** misconfiguration surfaces in deploy/CI, not on the first
production request.

**Acceptance Criteria**:
- [x] Given a controller whose constructor dependency cannot be resolved, when routes are registered, then registration raises (fail fast at boot).
- [x] Given a correctly-wired controller, when the app boots, then all routes mount and serve requests.

**Security Requirements**:
- [x] None.

**Documentation Requirements**:
- [x] None beyond Story 1.

**Requirement Refs**: SPEC-3
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001 (ORM).

## Notes
- D2 (cleanup): the DB-transaction middleware's exception handler was written as the
  Python-2-looking `except TypeError, ValueError:`. It works on 3.14 (parses as a
  tuple) but was parenthesized for clarity. Covered by SPEC-5.
- Deferred follow-ups (separate work items):
  - `auth/provider._mount_routes` captures a controller instance at boot via closures
    (same shape as this defect, different code path; auth module audit).
  - Per-request DI child container — `request.state.arvel_scope` is currently the
    root container, so `Container.scoped()` bindings are not request-isolated.
  - Rate-limit header parity (`X-RateLimit-Reset`, headers on non-`Response` returns,
    `Retry-After` from `reset_at`).
