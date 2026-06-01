# ADR-041 — DB.transaction() uses begin_nested() for nesting

**Status**: Accepted
**Date**: 2026-05-18

## Context

`DB.transaction()` needs to work both when called standalone (no active session) and when called
inside an HTTP request (active session exists from `DatabaseTransaction` middleware). Two options:
(a) always open a new connection, or (b) detect active session and use `begin_nested()` (savepoint).

## Decision

Detect active session via `get_active_session()`. If a session exists, use `begin_nested()` (SAVEPOINT).
If no session exists, open a new session from `async_sessionmaker`.

## Rationale

- A second connection in the same request means two separate transactions — reads in the outer transaction are not visible to the inner transaction and vice versa. That breaks correctness.
- Savepoints have correct nested semantics: inner rollback rolls back only to the savepoint; outer transaction can still commit.
- All supported databases (MySQL 8+, PostgreSQL, SQLite ≥ 3.25) support `SAVEPOINT` syntax.
- Compatible with HTTP middleware: the middleware session is reused, not replaced.

## Alternatives Rejected

- **Always open new connection**: Two-connection scenarios have visibility and consistency problems. Rejected.
