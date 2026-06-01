# ADR-046 — Migration reversibility enforced at registration time

**Status**: Accepted
**Date**: 2026-05-17

## Context

Irreversible migrations are a production-day-one footgun. A developer drops a
column in `up()` and leaves `down()` empty, and the team discovers it only
when a rollback fails at 3 AM.

Three options:

| Option | Pros | Cons |
|---|---|---|
| A. Trust developers — no enforcement | Zero overhead | The 3 AM scenario |
| B. Enforce at apply time (`migrate` refuses irreversible) | Catches before damage | Late — the migration is already merged to main; rollback path is broken in CI |
| C. **Enforce at registration time** (file load) | Catches at the unit test boundary; CI rejects merge | Slightly trickier — we have to introspect the `up()` callable |

## Decision

Option C. When the migration runtime loads a `Migration` subclass file:

1. Parse `up()`'s AST.
2. Walk for calls to `Schema.drop`, `Schema.drop_if_exists`, or any `.drop_column(...)`.
3. If found:
   - Parse `down()`'s AST.
   - If `down()` is empty (only `pass` or only a docstring), raise
     `MigrationNotReversibleError` at registration time.
   - If `down()` has at least one statement, accept (we trust the author wrote
     a real reverse; we don't try to prove semantic equivalence).

The check is purely structural — we don't validate the reverse is correct,
only that the author wrote *something*. Real semantic reversibility is
enforced by the test in `tests/database/test_migration_reversibility.py`,
which applies and rolls back every committed migration against an in-memory
SQLite during CI.

## Consequences

**Positive**:
- Drops without downs are caught at the pytest collection stage — instant
  feedback in the developer's editor.
- Combined with the CI apply-then-rollback test, the team gets two layers of
  defense: structural (registration) + semantic (test).
- Zero runtime overhead in production (the check runs at module import,
  which is once per process).

**Negative**:
- AST introspection of `up()` adds a small import-time cost. Migrations are
  imported lazily (only when `migrate` runs in production, or during the
  apply-then-rollback test in CI), so this is acceptable.
- A `down()` that does literally nothing meaningful (e.g. just a print
  statement) will pass the structural check. The semantic test in CI catches
  it on the rollback attempt.

**Enforcement**:
- `tests/database/test_migration_reversibility.py` parses every committed
  migration, then applies+rolls back against in-memory SQLite.
- Migration runtime raises `MigrationNotReversibleError` on registration
  with a clear message naming the operation and the offending file.
