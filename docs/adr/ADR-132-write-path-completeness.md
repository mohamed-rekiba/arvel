# ADR-132: Write-path completeness (insert_or_ignore / upsert count / truncate / insert_using / increment_each)

Status: Accepted (delivered WI-arvel-011)

Eloquent-parity increment (backlog `005`, story S8). No HTTP or schema surface —
recorded as an ADR. Builds on the WHERE-predicate engine (ADR-130).

## ADR-132-01: `upsert` issues one multi-row statement and returns a count

Status: Accepted

The old `upsert` looped per row, firing one `ON CONFLICT DO UPDATE` statement each and
returning `None`. Laravel's `upsert` runs a single multi-row statement and returns the
affected count. We now build one `insert(table).values(rows)` and attach the dialect's
conflict clause (`on_conflict_do_update` on SQLite/PostgreSQL, `on_duplicate_key_update`
on MySQL), then return `result.rowcount` (falling back to `len(rows)` when a driver
reports `-1`).

The native path only fires when every `unique_by` column is backed by the table's PK or a
`UNIQUE` constraint — `ON CONFLICT` needs a real conflict target. When it isn't, we fall
back to `_upsert_manual`, a per-row check-and-write that still returns a meaningful count.

## ADR-132-02: `insert_or_ignore` is dialect-routed, not emulated

Status: Accepted

`insert_or_ignore` emits `ON CONFLICT DO NOTHING` (SQLite/PostgreSQL) or `INSERT IGNORE`
(MySQL) as a single multi-row statement and returns rows inserted. Unknown dialects fall
back to a plain insert (no suppression) rather than a slow per-row existence probe — if a
dialect can't express "ignore conflicts" cheaply, silently emulating it would hide a
correctness gap.

## ADR-132-03: `truncate` is a hard wipe, dialect-aware

Status: Accepted

PostgreSQL/MySQL run `TRUNCATE TABLE <quoted>` — the table identifier comes from the model
(trusted) and is quoted via the dialect's `identifier_preparer`, so there's no injection
surface. SQLite has no `TRUNCATE`, so it falls back to `DELETE` without a WHERE.

`truncate` ignores soft-delete entirely — it removes every row (and resets identity on
PG/MySQL). Use `Model.where(...).delete()` for a soft-delete-aware wipe. This is documented
in `database.md` so the difference from `delete()` is explicit.

## ADR-132-04: `insert_using` reuses the source builder's compiled SELECT

Status: Accepted

`insert_using(columns, query)` builds `INSERT INTO table (columns) SELECT …` via SQLAlchemy
`insert().from_select(columns, select)`. The source `select` is the query builder's
`apply_global_scopes()` output, so global scopes (e.g. soft-delete filtering) on the source
model are honored — the rows copied in are the rows the source query would have returned.

## ADR-132-05: `increment_each` / `decrement_each` bump many columns in one UPDATE

Status: Accepted

Both build a single `UPDATE` whose SET list is `{col: column + delta}` per entry, reusing
the same `_touch_updated_at` and global-scope WHERE plumbing as the single-column
`increment`. `decrement_each` negates the deltas and delegates. One round trip, not N.
