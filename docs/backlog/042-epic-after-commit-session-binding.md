# Epic: After-commit callbacks must run after the session is closed, not while it's still bound

## Summary
The `DatabaseTransaction` HTTP middleware fired `DB.after_commit` callbacks inside
the `async with maker() as session` block, after the COMMIT but before the session
was unbound. A callback writing through the active session opened a fresh implicit
transaction that got silently rolled back on close. `DB.transaction()` already fires
callbacks after the session is closed/unbound — align the middleware.

**Module:** DB transactions · **Spec:** `docs/pipeline/specs/WI-arvel-042-after-commit-session-binding.md`

## Stories

### Story 1: After-commit callbacks run with no active session
**As a** developer registering `DB.after_commit` work in a request, **I want** it to
run after the transaction is fully done, **so that** any DB access inside it opens its
own transaction instead of being silently discarded.

**Acceptance Criteria**:
- [ ] Given a 2xx response, when after-commit callbacks fire, then `get_optional_session()` is None inside them.
- [ ] Given a 4xx/5xx response, when the request finishes, then callbacks do not fire (rollback).
- [ ] Given an exception, when the request unwinds, then callbacks do not fire and the error propagates.
- [ ] The middleware's after-commit semantics match `DB.transaction()`.

**Security Requirements**:
- [ ] No silent data loss: a callback's writes are never discarded without error (A10).

**Requirement Refs**: SPEC-1
**Priority**: Should · **Complexity**: Small · **Status**: Done

## Dependencies
- Shares the after-commit queue contextvar in `arvel/database/session.py`.

## Notes
- `DB.transaction`, `transactional` (deadlock/serialization retry), the imperative
  begin/commit/rollback stack, `autocommit`, `pretend`, and raw SQL were audited and
  found sound.
- Deferred: per-savepoint after-commit scoping (a callback under a rolled-back
  savepoint still fires at the outer commit) — Laravel discards it; edge case.
