# Epic: Query Builder Parity with Laravel

## Summary

Close the feature gap between Arvent's query builder (`packages/arvel/src/arvel/database/query.py`)
and Laravel's mature query builder. Findings come from a five-dimension parity review against the
Laravel source in `repos/lv-app/vendor/laravel`. This epic covers clause building, execution,
writes, pagination, streaming, and debugging. Relationship and model-attribute parity live in
epics 006 and 007.

Arvel's happy path (core `where`, `where_in`, joins, locks, unions, `when`, aggregates, basic
pagination) is solid. The stories below target the variants and ergonomics that ported Laravel
code expects to find.

## Stories

### Story 1: Date/time WHERE helpers
**As a** developer filtering by timestamps, **I want** `where_date`/`where_time`/`where_day`/`where_month`/`where_year` (and `or_*` variants), **so that** I can filter on date parts without hand-writing `func.date()`/`extract()` per dialect.

**Acceptance Criteria**:
- [x] Given a datetime column, when I call `where_year("created_at", 2026)`, then the SQL filters by the year using dialect-appropriate extraction (SQLite, PostgreSQL).
- [x] Given each helper, when used, then an `or_*` variant exists and composes correctly with other clauses.
- [x] Given an invalid column, when called, then it raises the same error type as other `where_*` helpers.

**Security Requirements**:
- [x] All values are parameterized — no string interpolation of user input into SQL.

**Documentation Requirements**:
- [x] `docs/guides/` query builder reference gains a date-filter section.

**Priority**: Should
**Complexity**: Medium
**Status**: DONE — WI-arvel-009, ADR-131 (`test_qb_date_filters.py`). `extract()` compiles to
EXTRACT (PG) / STRFTIME (SQLite); `where_date`/`where_time` compose year/month/day + h/m/s.

### Story 2: Nested WHERE groups (closure grouping)
**As a** developer building dynamic filters, **I want** `where(lambda q: q.where(...).or_where(...))` to produce a parenthesized boolean group, **so that** I can express `(A AND B) OR C` trees without dropping to raw SQLAlchemy.

**Acceptance Criteria**:
- [ ] Given a closure passed to `where`, when compiled, then its conditions are wrapped in parentheses and joined with the outer boolean.
- [ ] Given `or_where(closure)`, when compiled, then the group is OR-joined to the preceding clause.
- [ ] Nested closures (group within group) compile correctly.

**Documentation Requirements**:
- [ ] Document grouped-where with a `(A AND B) OR C` example.

**Priority**: Must
**Complexity**: Medium

### Story 3: Subquery FROM / JOIN / SELECT
**As a** developer writing reporting queries, **I want** `from_sub`, `join_sub`/`left_join_sub`, `select_sub`, and `add_select`, **so that** I can build derived-table and ranked-subquery queries the way Laravel does.

**Acceptance Criteria**:
- [x] Given a sub-builder, when passed to `from_sub(qb, alias)`, then the outer query selects from the aliased derived table.
- [x] Given `join_sub(qb, alias, on)`, when compiled, then the subquery joins as a table with the given ON condition.
- [x] Given `select_sub(qb, alias)` and `add_select(*cols)`, then columns are appended (not replaced) on the SELECT list.

**Priority**: Should
**Complexity**: Large
**Status**: DONE — WI-arvel-012, ADR-133 (`test_qb_subqueries.py`). `from_sub` (derived
table → dict rows), `join_sub`/`left_join_sub` (closure receives the aliased subquery),
`select_sub` (correlated scalar subquery as a labeled column), `add_select` (append model
columns or SQLAlchemy expressions). Appended columns attach onto the model instance.

### Story 4: `unless` and `tap` conditional chaining
**As a** developer porting Laravel code, **I want** `unless(cond, cb, default=None)` and `tap(cb)`, **so that** inverse-conditional and mid-chain inspection read the same as Laravel.

**Acceptance Criteria**:
- [ ] Given `unless(False, cb)`, when called, then `cb` runs; given `unless(True, cb)`, then it doesn't.
- [ ] Given `tap(cb)`, when called, then `cb` receives the builder and the original builder is returned unchanged.

**Priority**: Should
**Complexity**: Small

### Story 5: LIKE helpers and multi-column WHERE sugar
**As a** developer building search, **I want** `where_like`/`where_not_like` (with case-sensitivity flag) and `where_all`/`where_none` across columns, **so that** search filters don't need manual `or_()`/`ilike` assembly.

**Acceptance Criteria**:
- [x] Given `where_like("name", term, case_sensitive=False)`, then it emits `ILIKE` (PG) / `LIKE` with case folding as appropriate.
- [x] Given `where_all(cols, op, value)`, then all columns are AND-matched; `where_none` produces the NOR form.
- [x] `where_any` is extended to accept the same operator signature as Laravel.

**Security Requirements**:
- [x] LIKE wildcards in user input are handled safely (parameterized; document escaping for literal `%`/`_`).

**Priority**: Should
**Complexity**: Medium
**Status**: DONE — WI-arvel-009, ADR-131 (`test_qb_like_and_joins.py`). `where_like`/`not_like`
(+`or_`), `where_all`/`where_none`/`or_where_any`. SQLite LIKE is ASCII-case-insensitive by
design; the flag selects LIKE vs ILIKE (case-sensitive on PG).

### Story 6: Join completeness (right/cross + fluent ON)
**As a** developer, **I want** `right_join`, `cross_join`, and a closure-based ON builder with `on`/`or_on`, **so that** join construction matches Laravel's `JoinClause`.

**Acceptance Criteria**:
- [x] Given `right_join`/`cross_join`, when compiled, then they emit the correct join type.
- [x] Given a join closure, when it chains `on(...).or_on(...)`, then the ON clause compiles with the right boolean grouping.

**Priority**: Could
**Complexity**: Medium
**Status**: DONE — WI-arvel-009, ADR-131 (`test_qb_like_and_joins.py`). `cross_join`, fluent
`join_on(target, lambda j: j.on(...).or_on(...))`; `right_join` rewritten as
`target LEFT OUTER JOIN model` (SQLAlchemy has no native RIGHT JOIN).

### Story 7: Efficient `exists()` / `doesnt_exist()`
**As a** developer doing existence checks, **I want** `exists()` to run `SELECT EXISTS(SELECT 1 ... LIMIT 1)` and a `doesnt_exist()` companion, **so that** auth/validation checks don't pay for a full `COUNT(*)` subquery.

**Acceptance Criteria**:
- [ ] Given `exists()`, when executed, then it emits an `EXISTS`-based query, not `count() > 0`.
- [ ] Given `doesnt_exist()`, then it returns the negation.
- [ ] Existing call sites that relied on `exists()` keep their behavior (regression tests pass).

**Priority**: Must
**Complexity**: Small

### Story 8: Write-path completeness
**As a** developer running idempotent ingests, **I want** `insert_or_ignore`, a batched dialect-complete `upsert` (returning affected count), `truncate`, `insert_using`, and `increment_each`/`decrement_each`, **so that** sync and bulk flows match Laravel.

**Acceptance Criteria**:
- [x] Given `insert_or_ignore(rows)`, then it emits `ON CONFLICT DO NOTHING` (PG/SQLite) / `INSERT IGNORE` (MySQL).
- [x] Given `upsert(rows, unique_by, update)`, then it issues a single multi-row statement (not a per-row loop) and returns the affected row count.
- [x] Given `truncate()`, then it truncates the mapped table; soft-delete policy interaction is documented.
- [x] Given `increment_each({...})`, then multiple columns are bumped in one statement.

**Security Requirements**:
- [x] All values parameterized; `unique_by` columns validated against the model.

**Priority**: Should
**Complexity**: Large
**Status**: DONE — WI-arvel-011, ADR-132 (`test_qb_write_path.py`). `insert_or_ignore`
(ON CONFLICT DO NOTHING / INSERT IGNORE), single-statement `upsert` returning affected
count (manual fallback when no PK/UNIQUE backs `unique_by`), `truncate` (TRUNCATE on
PG/MySQL, DELETE on SQLite — hard wipe, bypasses soft-delete), `insert_using` (INSERT …
SELECT), `increment_each`/`decrement_each` (multi-column in one UPDATE).

### Story 9: Pagination HTTP + JSON parity
**As a** frontend consumer, **I want** `paginate`/`simple_paginate`/`cursor_paginate` to support `page_name`, request page resolution, `appends`/`with_query_string`/`fragment`, an `on_each_side` link window, bidirectional cursors, and a Laravel-shaped JSON envelope, **so that** Arvel endpoints are drop-in compatible with Laravel API clients and resources.

**Acceptance Criteria**:
- [ ] Given a request, when `paginate()` is called without an explicit page, then the current page resolves from the configured `page_name` query param.
- [ ] Given a paginator result, when serialized, then it can emit Laravel's flat envelope (`current_page`, `data`, `next_page_url`, `path`, `from`, `to`, `total`, ...).
- [ ] Given `cursor_paginate()`, then both `next_cursor` and `prev_cursor` are produced and a previous page can be fetched.
- [ ] Given `appends({...}).with_query_string()`, then generated URLs preserve query parameters.

**Documentation Requirements**:
- [ ] Document the JSON envelope shapes and the cursor encoding.

**Priority**: Should
**Complexity**: Large

### Story 10: Streaming and chunking completeness
**As a** developer exporting large tables, **I want** a true server-side `stream()` (driver cursor), descending keyset chunk/lazy variants, `each_by_id`, callback early-termination, and an order-by guard, **so that** large-data iteration is memory-safe and matches Laravel's chunking guarantees.

**Acceptance Criteria**:
- [x] Given `stream()`, when iterated, then rows are fetched one batch at a time via SQLAlchemy `stream_scalars()` (distinct from the keyset `lazy()` alias).
- [x] Given `chunk_by_id(..., descending=True)` and a `lazy_by_id` desc variant, then iteration walks keyset in the requested direction.
- [x] Given a `chunk` callback that returns `False`, then iteration stops.
- [x] Given offset-based `chunk`/`each` without an order, then it auto-orders by primary key (Eloquent-parity; documented in queries.md).

**Priority**: Should
**Complexity**: Medium
**Status**: DONE — WI-arvel-007, ADR-129 (`test_streaming_completeness.py`)

### Story 11: Debugging and query-log parity
**As a** developer debugging SQL, **I want** session-level query logging (`{sql, bindings, time_ms}`), a `pretend`/dry-run mode, `explain()`, `to_raw_sql()`, and `get_bindings()`, **so that** I can inspect and snapshot all ORM traffic, not just raw-SQL helpers.

**Acceptance Criteria**:
- [ ] Given query logging enabled, when any `QueryBuilder` executes, then the statement, bindings, and elapsed time are captured.
- [ ] Given `pretend()`, when writes run inside it, then SQL is recorded but not executed.
- [ ] Given `explain()`, then it returns the dialect's plan rows.

**Priority**: Could
**Complexity**: Medium

### Story 12: Transaction retry on deadlock
**As a** developer under concurrent writes, **I want** `DB.transaction(..., attempts=N)` to retry on deadlock/serialization failures, plus imperative `begin`/`commit`/`rollback`, **so that** transient lock conflicts don't surface as hard errors.

**Acceptance Criteria**:
- [x] Given `attempts=3`, when a deadlock/serialization error is raised, then the transaction body re-runs up to the limit before propagating.
- [x] Given a non-retryable error, then it propagates immediately without retry.
- [x] Imperative `begin_transaction`/`commit`/`rollback` exist and interoperate with savepoints.

**Priority**: Should
**Complexity**: Medium
**Status**: DONE — retry: WI-arvel (ADR-126, `test_transaction_retry.py`); imperative
control: WI-arvel-010, ADR-126-03 (`test_transaction_imperative.py`). Frame-stack
`begin_transaction`/`commit`/`rollback`; nested calls and calls inside `DB.transaction()`
open savepoints; after-commit callbacks fire on the outermost imperative commit.

### Story 13: Clause polish bundle (or_* / having / ordering / pluck)
**As a** developer, **I want** the remaining clause variants — `or_where_in/null/raw/between`, operator-form `having` + `having_null/between`, `reorder`, `in_random_order`, `order_by_desc`, `group_by_raw`, `pluck(value, key)` returning a dict, `count(column)`, and `sum()` defaulting to 0 — **so that** common Laravel idioms have a direct Arvel equivalent.

**Acceptance Criteria**:
- [x] Each listed method exists with Laravel-equivalent semantics and is covered by a unit test.
- [x] `pluck("name", "id")` returns `{id: name}`; `sum()` over an empty set returns `0`.

**Priority**: Could
**Complexity**: Medium
**Status**: DONE — WI-arvel-008, ADR-130 (`test_qb_clause_polish.py`). Includes the WHERE
predicate engine (real `or_where`/`or_where_*` OR-onto-chain) and the clause-variant bundle.

## Dependencies

- Story 9 (pagination JSON) pairs with epic 006's serialization work for end-to-end API parity.
- Story 12 (transaction retry) is shared infra also referenced by epic 006's `*Quietly` write methods.

## Notes

- Laravel references: `repos/lv-app/vendor/laravel/framework/src/Illuminate/Database/Query/Builder.php`,
  `Eloquent/Builder.php`, `Concerns/BuildsQueries.php`, `Pagination/*`.
- Keep every clause parameterized through SQLAlchemy's expression engine — no `text(f"...")` with
  user input (see `310-security.mdc` A05).
