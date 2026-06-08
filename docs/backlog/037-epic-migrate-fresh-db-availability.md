# Epic: Destructive migration commands fail gracefully when the DB is down

## Summary
`migrate:fresh` and `migrate:refresh` must pre-flight the database connection and exit
with code 2 and a clear message when it's unavailable — matching `migrate` — instead
of leaking a raw driver traceback and exiting 1.

**Module:** migrations · **Spec:** `docs/pipeline/specs/WI-arvel-037-migrate-fresh-db-availability.md`

## Stories

### Story 1: Friendly failure on an unreachable database
**As an** operator running `migrate:fresh`/`migrate:refresh` against a down database,
**I want** a clear "database is not available" message and exit code 2, **so that** I
get the same actionable failure as `migrate` instead of a stack trace.

**Acceptance Criteria**:
- [ ] Given the DB is unreachable, when `migrate:fresh` runs, then it exits 2 with the friendly message and drops nothing.
- [ ] Given the DB is unreachable, when `migrate:refresh` runs, then it exits 2 with the friendly message.
- [ ] Given the DB is reachable, when either runs, then behaviour is unchanged.

**Security Requirements**:
- [ ] No raw driver traceback / internal path leaks to the operator on a DB outage (A10).

**Requirement Refs**: SPEC-1
**Priority**: Should · **Complexity**: Small · **Status**: Done

## Dependencies
- Reuses `arvel.database.health.check_database_connection` (already used by `migrate`).

## Notes
- Migrator core audited and found sound; no change there. Deferred parity-additive
  items: `--step` for migrate/rollback, status of orphaned applied migrations, SQLite
  batch-mode alters.
