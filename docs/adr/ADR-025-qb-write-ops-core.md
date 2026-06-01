# ADR-025: QB Write Ops Use SQLAlchemy Core, Not ORM Unit-of-Work

**Status**: Accepted
**Date**: 2026-05-18

## Decision

`QueryBuilder.insert`, `update`, `delete`, `upsert`, `truncate` use SQLAlchemy Core `insert()`/`update()`/`delete()` statements executed directly against the active `AsyncSession`.

## Context

SQLAlchemy offers two paths for mutations: the ORM unit-of-work (session.add / session.flush) and Core DML (`session.execute(insert(...))`). Bulk operations on the QB need to be single SQL statements, not per-row flushes.

## Consequences

- **Single SQL statement** regardless of record count — no N+1 on bulk inserts
- **Identity map bypass** — inserted/updated rows are NOT loaded into the session identity map (intentional — matches Laravel's `DB::table()` semantics)
- Callers who need freshly-hydrated models after a bulk insert should follow with a SELECT (explicit)
- `rowcount` is returned for `update` and `delete`
- Dialect support: `upsert` requires dialect-specific handling (PostgreSQL `ON CONFLICT DO UPDATE`, MySQL `ON DUPLICATE KEY UPDATE`, SQLite `ON CONFLICT`)
