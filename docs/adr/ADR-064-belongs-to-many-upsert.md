# ADR-064 — BelongsToMany Pivot Attach: UPSERT on PK Conflict

**Date**: 2026-05-17
**Status**: Accepted
**Deciders**: Solution Architect

---

## Context

`PivotProxy.attach(id_or_model, **pivot)` needs to handle the case where the pivot row already exists. Two options:

1. **Hard INSERT — fail on conflict**: caller must call `detach()` first; idempotent calls are not safe
2. **UPSERT (INSERT … ON CONFLICT DO UPDATE)**: idempotent; pivot columns are updated on re-attach

## Decision

Use **UPSERT** (`INSERT … ON CONFLICT (fk, rfk) DO UPDATE SET …pivot_cols`).

## Rationale

- Idempotent calls are a common pattern — `sync()` calls `attach()` for each ID; hard-INSERT would require a prior `detach()` dance
- Matches Laravel's `attach()` behaviour when called on an already-attached ID with `touch=true`
- SQLAlchemy's `insert().prefix_with("OR REPLACE")` (SQLite) and `on_conflict_do_update()` (PostgreSQL) cover both supported backends without raw SQL
- No data loss risk: pivot columns are updated to the latest values on conflict

## Consequences

- `PivotProxy.attach()` never raises `IntegrityError` for duplicate PK — callers cannot distinguish "new attach" from "update attach" without inspecting the result
- `PivotProxy.attach()` returns a `bool` — `True` if the row was newly inserted, `False` if updated — via `rowcount` heuristic
- Callers that need a "fail if already attached" semantic must call `PivotProxy.exists(id)` first (explicit over implicit)
- `sync()` uses UPSERT + DELETE-where-not-in — single round trip for PostgreSQL using `executemany` + UPSERT + `DELETE WHERE id NOT IN (...)`
