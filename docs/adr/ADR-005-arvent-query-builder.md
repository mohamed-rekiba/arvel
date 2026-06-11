# ADR-005 — Arvent — Query Builder

**Status**: Accepted
**Date**: original decisions 2026-05-17 – 2026-05-23; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: Eloquent-style query builder over SQLAlchemy 2.0 — write ops, table-mode QB, Collection, kwarg shorthand, predicate engine, conditional groups, subqueries, write-path completeness, debugging, streaming, pagination, helpers, FTS thin helpers, transactions, recursive CTEs.

## Why this is one ADR

Arvent's QB is one piece of code — all eighteen ADRs describe joints of the same builder. Read together they show a Laravel-faithful API mapped onto SQLAlchemy primitives.

---

## § 1 — QB Write Ops Use SQLAlchemy Core, Not ORM Unit-of-Work

**Originally**: ADR-025 · Date: 2026-05-18

### Decision

`QueryBuilder.insert`, `update`, `delete`, `upsert`, `truncate` use SQLAlchemy Core `insert()`/`update()`/`delete()` statements executed directly against the active `AsyncSession`.

### Context

SQLAlchemy offers two paths for mutations: the ORM unit-of-work (session.add / session.flush) and Core DML (`session.execute(insert(...))`). Bulk operations on the QB need to be single SQL statements, not per-row flushes.

### Consequences

- **Single SQL statement** regardless of record count — no N+1 on bulk inserts
- **Identity map bypass** — inserted/updated rows are NOT loaded into the session identity map (intentional — matches Laravel's `DB::table()` semantics)
- Callers who need freshly-hydrated models after a bulk insert should follow with a SELECT (explicit)
- `rowcount` is returned for `update` and `delete`
- Dialect support: `upsert` requires dialect-specific handling (PostgreSQL `ON CONFLICT DO UPDATE`, MySQL `ON DUPLICATE KEY UPDATE`, SQLite `ON CONFLICT`)

---

## § 2 — TableQueryBuilder Is a Separate Class

**Originally**: ADR-026 · Date: 2026-05-18

### Decision

`DB.table("users")` returns a `TableQueryBuilder` — a separate, non-generic class that is NOT a subclass of `QueryBuilder[T]`.

### Context

`QueryBuilder[T]` is bound to a specific SQLAlchemy `DeclarativeBase` model (`T`). It returns hydrated model instances. `DB.table()` should return raw dictionaries and accept any table name at runtime.

### Options

**A. `QueryBuilder[dict]`** — reuse the same class with `T = dict`. Technically possible but semantically misleading; the existing QB has model-specific logic (global scopes, relations) that doesn't apply to raw table access.

**B. Separate `TableQueryBuilder`** ← chosen. Clear separation of concerns; cleaner types; no leakage of model-specific QB behavior into raw table queries.

### Consequences

- `DB.table("users").get()` returns `list[dict[str, Any]]`
- `DB.table(...)` methods are a subset of `QueryBuilder` — no relations, no scopes, no soft-delete
- Duplication of some QB plumbing is acceptable; both classes share an internal `_execute_select` utility

---

## § 3 — Collection[T] Is a list[T] Subclass

**Originally**: ADR-027 · Date: 2026-05-18

### Decision

`Collection[T]` inherits from `list[T]`. All existing code that type-hints or calls `isinstance(result, list)` continues to work without modification.

### Context

Arvel's QB currently returns `list[T]`. Adding Laravel-style collection methods (`map`, `filter`, `pluck`, `group_by`, etc.) requires a richer type. Two paths exist.

### Options

**A. Wrapper class** — `Collection[T]` holds an internal `list[T]` and does NOT inherit from `list`. Clean OOP design but breaks all existing callers that use `list` type hints or `isinstance(..., list)`.

**B. `list[T]` subclass** ← chosen. `isinstance(collection, list)` returns `True`. All `list` methods are available. Chainable methods return `Collection` instances. Zero migration cost.

### Tradeoffs

- Subclassing `list` has subtle Python gotchas (e.g., `list.copy()` returns a `list`, not `Collection`). Affected built-in methods are overridden to return `Collection` where needed.
- `mypy --strict` handles `list` subclasses correctly when `Generic[T]` is explicitly declared.
- Performance: no overhead over a plain list for existing callers.

---

## § 4 — Kwarg-shorthand `where(col=value)` binds parameters via `getattr`, never string SQL

**Originally**: ADR-029 · Date: 2026-05-17

### Context

Eloquent's loose form (`User::where('email', $email)`) is convenient. Django's
`User.objects.filter(email=email)` is more convenient. Both have produced SQLi
bugs in the wild when implementers got lazy and string-concatenated the column
name into the SQL fragment.

Three options for the kwarg-shorthand path:

| Option | Pros | Cons |
|---|---|---|
| A. Reject kwarg-shorthand entirely — column-expression only | Eliminates the SQLi class | Fights Eloquent muscle memory; ugly for ad-hoc filters |
| B. Accept kwarg-shorthand but f-string the column name into the SQL | Convenient | **Critical** SQLi vector if a user's column name comes from external input |
| C. **Accept kwarg-shorthand; resolve `getattr(model, key)` to a typed `InstrumentedAttribute`** | Convenient AND safe | Slightly more work in the builder; raises `AttributeError` at call time on unknown columns |

### Decision

Option C. The implementation:

```python
def where(self, *clauses: ColumnElement, **kwargs: Any) -> Self:
    new = self._clone()
    for clause in clauses:
        new._where_clauses.append(clause)
    for key, value in kwargs.items():
        col = getattr(self._model, key)        # AttributeError if unknown
        if not isinstance(col, InstrumentedAttribute):
            raise AttributeError(f"{self._model.__name__}.{key} is not a column")
        new._where_clauses.append(col == value)
    return new
```

Same rule applies to `where_in`, `where_between`, `or_where`, `having`,
`group_by`, `order_by`, `pluck`, `value`. Any place a column name might be
named-by-string must route through `getattr`.

### Consequences

**Positive**:
- SQLi vector closed at the type-system level — `getattr` returns a Python
  attribute, not a string fragment.
- Unknown columns fail loudly at call time, not at query execution.
- The implementation is small (one `getattr` per kwarg).

**Negative**:
- Users who genuinely need to filter by a dynamic column name must use
  `getattr(Model, dynamic_name)` themselves, not the kwarg form. The DX docs
  document this with a security callout.

**Enforcement**:
- `tests/security/test_query_safety.py` covers every query-builder method
  with attacker-controlled values and column names.
- Stage 4b SQLi sweep is the centerpiece security gate for WI-003.
- Code review checklist: "Does this method accept a column name as a string
  and pass it through anywhere other than `getattr`?" → reject.

---

## § 5 — WHERE Predicate Engine and Clause Polish

**Originally**: ADR-030

Status: Accepted

Eloquent-parity increment (backlog `005`, story S13). Foundational change to how the
query builder accumulates `WHERE`, plus the remaining clause-variant bundle.

### ADR-005 § 5-01: WHERE lives in a builder predicate, not on the `Select`

Status: Accepted

`QueryBuilder` now accumulates its `WHERE` in a single `_where_predicate: ColumnElement[bool]
| None` instead of chaining `Select.where()` calls. This is what makes a real `or_where`
possible: SQLAlchemy's `Select.where()` only ever ANDs, so the old `or_where` could not OR a
condition onto the already-accumulated chain. The predicate is applied to the statement in
`apply_global_scopes()` and in the `statement` property, so every read/write path sees it.

`_and(cond)` / `_or(cond)` combine onto the predicate. All `where_*` helpers route through
`_and`; the `or_where_*` family routes through `_or`. Global scopes (e.g. soft-delete) run as
builder transforms, so their predicates compose correctly and an AND-ed scope wraps the whole
OR group — `(a OR b) AND deleted_at IS NULL` — which is safer than Laravel's flat precedence.

### ADR-005 § 5-02: `or_where` ORs onto the whole chain, with explicit grouping

Status: Accepted

`where(a).or_where(b).where(c)` produces `(a OR b) AND c` — explicit, parenthesized grouping.
This differs from Laravel's flat, precedence-driven `a OR b AND c` (= `a OR (b AND c)`), a
known footgun. Arvel chooses explicit grouping deliberately: it's predictable and keeps
global scopes (soft deletes, tenancy) ANDed around the entire user predicate. New `or_where_in`
/ `or_where_not_in` / `or_where_null` / `or_where_not_null` / `or_where_raw` / `or_where_between`
follow the same rule.

### ADR-005 § 5-03: Clause polish bundle

Status: Accepted

Added the remaining Laravel clause variants: `order_by_desc`, `reorder` (drop then optionally
re-set ORDER BY via `Select.order_by(None)`), `in_random_order` (`random()`), `group_by_raw`,
operator-form `having("total", ">", 5)` plus `having_null` / `having_between`, `pluck(value,
key)` returning a dict, `count(column)` (COUNT of non-null values), and `sum()` returning `0`
on an empty set (Laravel parity — the prior `None` behaviour was changed).

---

## § 6 — Query Builder Conditional Groups, `unless`/`tap`, and Efficient `exists`

**Originally**: ADR-031

Status: Accepted

Eloquent-parity increment (backlog `005`, Sprint A: stories S2, S4, S7). No HTTP or
schema surface — recorded as an ADR, not a SAD/OpenAPI spec.

### ADR-005 § 6-01: Nested `WHERE` groups via a callback that returns a builder

Status: Accepted

Laravel groups predicates by passing a closure that *mutates* a sub-builder:
`where(fn ($q) => $q->where('a', 1)->orWhere('b', 2))` → `(a = 1 or b = 2)`.

Arvel's builder is immutable (every clause returns a clone), so a mutate-in-place
closure can't work. Instead, a group callback receives a fresh empty builder and
**must return** the resulting builder. We read its accumulated predicate via
`Select.whereclause` and splice that single grouped expression into the parent.
SQLAlchemy parenthesizes the spliced `BooleanClauseList` automatically, so mixing
`AND`/`OR` levels stays correct.

Grouping semantics follow Arvel's *existing* builder, which differs from Laravel's
closure-internal boolean chaining. A group callback is a single predicate term you
pass into `where(...)` (ANDed) or `or_where(...)` (ORed alongside that call's other
terms). `or_where` ORs its own arguments and ANDs the result onto the chain — it
does **not** OR against preceding `where`s. So:

- `where(lambda q: q.or_where(A, B)).where(C)` → `(A OR B) AND C`
- `or_where(A, lambda q: q.where(B).where(C))` → `A OR (B AND C)`

This keeps the existing `or_where` contract intact (no behavior change to a tested
method); the callback only adds parenthesized grouping.

A callback that returns `None` (or a non-builder) raises `TypeError` — fail loud,
because a silently dropped group is a data-correctness bug.

### ADR-005 § 6-02: `unless` is `when` with a negated condition; `tap` is side-effect only

Status: Accepted

`unless(cond, cb, otherwise=None)` delegates to `when(not cond, ...)` — one
implementation, no divergence. `tap(cb)` hands a clone to the callback for
inspection/logging and returns that clone unchanged; the callback's return value is
ignored, matching Laravel's `tap` contract (side effects, not transformation).

### ADR-005 § 6-03: `exists` issues `SELECT EXISTS(...)`, not `COUNT(*) > 0`

Status: Accepted

The old `exists()` ran `SELECT count(*) FROM (subquery)` then compared to zero —
the database materializes and counts every matching row. We now emit
`SELECT EXISTS (SELECT 1 FROM ... WHERE ... LIMIT 1)`, letting the planner
short-circuit on the first hit. Global scopes still apply (built on
`apply_global_scopes()`). `doesnt_exist()` is the negation.

---

## § 7 — Write-path completeness (insert_or_ignore / upsert count / truncate / insert_using / increment_each)

**Originally**: ADR-032

Status: Accepted (delivered WI-arvel-011)

Eloquent-parity increment (backlog `005`, story S8). No HTTP or schema surface —
recorded as an ADR. Builds on the WHERE-predicate engine (ADR-005 § 5).

### ADR-005 § 7-01: `upsert` issues one multi-row statement and returns a count

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

### ADR-005 § 7-02: `insert_or_ignore` is dialect-routed, not emulated

Status: Accepted

`insert_or_ignore` emits `ON CONFLICT DO NOTHING` (SQLite/PostgreSQL) or `INSERT IGNORE`
(MySQL) as a single multi-row statement and returns rows inserted. Unknown dialects fall
back to a plain insert (no suppression) rather than a slow per-row existence probe — if a
dialect can't express "ignore conflicts" cheaply, silently emulating it would hide a
correctness gap.

### ADR-005 § 7-03: `truncate` is a hard wipe, dialect-aware

Status: Accepted

PostgreSQL/MySQL run `TRUNCATE TABLE <quoted>` — the table identifier comes from the model
(trusted) and is quoted via the dialect's `identifier_preparer`, so there's no injection
surface. SQLite has no `TRUNCATE`, so it falls back to `DELETE` without a WHERE.

`truncate` ignores soft-delete entirely — it removes every row (and resets identity on
PG/MySQL). Use `Model.where(...).delete()` for a soft-delete-aware wipe. This is documented
in `database.md` so the difference from `delete()` is explicit.

### ADR-005 § 7-04: `insert_using` reuses the source builder's compiled SELECT

Status: Accepted

`insert_using(columns, query)` builds `INSERT INTO table (columns) SELECT …` via SQLAlchemy
`insert().from_select(columns, select)`. The source `select` is the query builder's
`apply_global_scopes()` output, so global scopes (e.g. soft-delete filtering) on the source
model are honored — the rows copied in are the rows the source query would have returned.

### ADR-005 § 7-05: `increment_each` / `decrement_each` bump many columns in one UPDATE

Status: Accepted

Both build a single `UPDATE` whose SET list is `{col: column + delta}` per entry, reusing
the same `_touch_updated_at` and global-scope WHERE plumbing as the single-column
`increment`. `decrement_each` negates the deltas and delegates. One round trip, not N.

---

## § 8 — Subquery FROM / JOIN / SELECT

**Originally**: ADR-033

Status: Accepted (delivered WI-arvel-012)

Eloquent-parity increment (backlog `005`, story S3). No HTTP or schema surface —
recorded as an ADR. Builds on the WHERE-predicate engine (ADR-005 § 5) and reuses the
existing row-shaping markers in `all()`.

### ADR-005 § 8-01: `on` is a callable that receives the aliased subquery

Status: Accepted

Laravel's `joinSub` takes a closure whose `JoinClause` exposes raw column strings. We need
the caller to reference the subquery's columns, but a derived table's columns only exist
once it's aliased. So `join_sub(query, alias, on)` builds the `subquery(alias)` first, then
calls `on(subq)` — the closure receives the alias and references columns the typed way:

```python
SqUser.join_sub(high_value, "hv", lambda hv: hv.c.user_id == SqUser.id)
```

`on` also accepts a bare condition for callers that already hold a reference. `left_join_sub`
is the `kind="left"` shortcut. The join doesn't touch the SELECT list, so results stay model
instances — pull subquery columns in explicitly with `add_select`/`select_sub` when needed.

### ADR-005 § 8-02: `from_sub` returns dicts, not model instances

Status: Accepted

`from_sub(query, alias)` replaces the FROM with `select(subq).select_from(subq)` and clears
the inherited WHERE predicate (the outer query operates on the derived table, not the model's
own columns). Because the rows no longer map to the model's mapped entity, `all()` returns
dicts — it reuses the existing `__cols__` marker that already yields `result.mappings()`
dicts. Typed `where()` on derived columns isn't supported; that's raw/derived-column
territory.

### ADR-005 § 8-03: `select_sub` / `add_select` append via the `__with_agg__` path

Status: Accepted

`select_sub(query, alias)` turns a single-column sub-builder into a correlated
`scalar_subquery().label(alias)` and appends it with `add_columns`. `add_select(*columns)`
appends model column names (resolved) or raw SQLAlchemy expressions. Both mark the builder
with the existing `__with_agg__` selector, so `all()` keeps the model entity in `row[0]` and
attaches the extra labeled columns onto each instance by name — the same mechanism
`with_count`/`with_sum` already use. This is why appended columns surface as attributes
(`user.top_amount`) rather than forcing a switch to dict rows.

---

## § 9 — Framework Query Builder Critical Fixes

**Originally**: ADR-034

See SAD-043 for full context. This ADR records the two non-obvious decisions.

### ADR-005 § 16-01: Route `Model.find()` through the query builder

Status: Accepted

Routing through the QB ensures global scopes (soft-delete, etc.) are applied consistently.
The identity map bypass is an acceptable trade-off for correctness.

### ADR-005 § 16-02: Raise `ValueError` on unknown `where_any()` operators

Status: Accepted

Silent equality fallback is a data-correctness bug masquerading as a feature.
Fail loudly, fail early.

---

## § 10 — Streaming and Chunking Completeness

**Originally**: ADR-035

Status: Accepted

Eloquent-parity increment (backlog `005`, Sprint B: story S10). No HTTP or schema
surface — recorded as an ADR.

### ADR-005 § 10-01: `stream()` is a true server-side cursor, distinct from `lazy()`

Status: Accepted

`lazy()` / `cursor()` walk a keyset in `LIMIT` batches — stable under concurrent writes
but issues N queries. `stream()` is the other tool: one statement, fetched incrementally
from the driver via SQLAlchemy `AsyncSession.stream_scalars()` with `yield_per`. It fires
`retrieved` per row and does **not** batch-eager-load pivot relations (there's no batch) —
use `lazy()`/`chunk()` when you need pivot eager-loading while streaming.

### ADR-005 § 10-02: Directional keyset — `descending=` on `chunk_by_id`, plus `lazy_by_id`

Status: Accepted

Keyset iteration gains a direction. `chunk_by_id(..., descending=True)` and the new
`lazy_by_id(..., descending=True)` order by the key column `DESC` and page with `col <
last` instead of `col > last`. `lazy()` stays the ascending shorthand. A shared
`_keyset_batches(size, column, descending)` generator backs `chunk_by_id`, `lazy`, and
`lazy_by_id` so the walk logic lives in one place.

### ADR-005 § 10-03: Callbacks can stop early by returning `False`

Status: Accepted

`chunk` / `chunk_by_id` / `each` callbacks may return `False` to stop iteration, matching
Eloquent. Returning `None` (or anything truthy) continues. Signatures widen to
`Awaitable[bool | None]`.

### ADR-005 § 10-04: Offset `chunk` enforces an order by primary key

Status: Accepted

Offset pagination without a stable order can skip or repeat rows. Rather than raise (the
base-query-builder behaviour), Arvel's model-bound builder follows Eloquent: if no
`order_by` is set, `chunk` (and `each`, which delegates to it) auto-orders by the model's
primary key. An explicit `order_by` is respected as-is.

---

## § 11 — Pagination HTTP + JSON parity

**Originally**: ADR-036

Status: Accepted (delivered WI-arvel-014)

Eloquent-parity increment (backlog `005`, story S9). Touches the HTTP middleware but adds no
new routes or schema — recorded as an ADR.

### ADR-005 § 11-01: Request resolution via a contextvar, not an HTTP import in the DB layer

Status: Accepted

Laravel resolves the current page/cursor from the global request. We don't want
`arvel.database` importing anything HTTP-specific, so the bridge is a contextvar:
`PaginationRequest(path, query)` lives in `arvel.database.paginator`, and
`ObservabilityMiddleware` sets it per request from the ASGI scope (`path` + parsed
`query_string`). The paginators call `resolve_page(page_name)`, `resolve_cursor(cursor_name)`,
and `resolve_path()` against it.

`paginate(per_page, page=None, page_name="page")` resolves the page when `page is None` (a
caller can still pin it explicitly). The path captured into the paginator at creation time is
used to build absolute links later.

### ADR-005 § 11-02: Two serialization shapes — `to_dict` (nested) and `to_response` (flat)

Status: Accepted

The existing `to_dict()` returns the project's `{data, meta, links}` nested envelope and stays.
`to_response()` is new and emits Laravel's **flat** envelope so ported API clients and
`JsonResource` consumers see the keys they expect:

- LengthAware: `current_page, data, first_page_url, from, last_page, last_page_url, links,
  next_page_url, path, per_page, prev_page_url, to, total`.
- Simple: same minus `total`/`last_page`/`links`.
- Cursor: `data, path, per_page, next_cursor, prev_cursor, next_page_url, prev_page_url`.

The `links` array is the windowed page list built from `on_each_side` (gaps rendered as
`"..."`) with the `&laquo; Previous` / `Next &raquo;` bookends and an `active` flag — byte-for-
byte the shape Laravel's `LengthAwarePaginator::toArray()` produces.

### ADR-005 § 11-03: `appends` / `with_query_string` / `fragment` are immutable chainables

Status: Accepted

`Paginator` is a frozen dataclass, so these return `dataclasses.replace` copies rather than
mutating. `appends(mapping)` adds query params carried on every URL; `with_query_string()`
pulls the current request's query (minus the page key) onto the paginator; `fragment(s)`
appends `#s`. The paginator owns the page key, so a request `?page=9` never leaks into the
generated `next`/`prev` URLs.

### ADR-005 § 11-04: Bidirectional cursors via a direction flag in the token

Status: Accepted

Cursor tokens become `base64(json({"_p": <keyset values>, "_n": <points_to_next>}))`. The
paginator emits **both** `next_cursor` and `prev_cursor`:

- Forward (no cursor or `_n=true`): order by the keyset, `WHERE keyset > cursor`, fetch
  `per_page + 1`. `next_cursor` if there's an overflow row; `prev_cursor` whenever we came
  from a prior page.
- Backward (`_n=false`): flip every column's direction, apply the inverse row-value
  comparison, fetch `per_page + 1`, then reverse the rows back to display order. A next page
  always exists (we walked back from it); `prev_cursor` only if there's an overflow row.

Because the user may have set their own `ORDER BY` before `cursor_paginate`, the method clears
ordering (`order_by(None)`) before applying the keyset order so direction is fully controlled.
Tokens stay opaque to callers; malformed tokens raise `InvalidCursorError`.

---

## § 12 — Debugging and query-log parity

**Originally**: ADR-037

Status: Accepted (delivered WI-arvel-013)

Eloquent-parity increment (backlog `005`, story S11). No HTTP or schema surface —
recorded as an ADR.

### ADR-005 § 12-01: Query logging hooks the engine, not the QueryBuilder

Status: Accepted

There's already a test helper (`QueryLog.capture()`) that listens on the bound engine for a
with-block. For a Laravel-style `DB::enableQueryLog()` we need the same coverage at the
facade level, capturing `{sql, bindings, time_ms}` for **all** traffic — query builder, raw
`DB.select`, relationship loads — not just statements that route through one method.

So `DB.enable_query_log()` installs `before_cursor_execute` / `after_cursor_execute`
listeners on `engine.sync_engine`. Every executed cursor is recorded regardless of which
Python API produced it. Timing uses a per-connection stack in `conn.info` (the SQLAlchemy-
recommended pattern) so nested/concurrent executions pair their start and end correctly.

The removers are kept in a **list** ClassVar rather than a bare `Callable` attribute —
storing a function directly on the class reads as a method definition to the type checker.

### ADR-005 § 12-02: `pretend` rolls back rather than truly skipping execution

Status: Accepted

Laravel's `pretend` flips a connection flag so writes are logged but never sent. Our async
SQLAlchemy stack has no single execution chokepoint to intercept, and faking result objects
for skipped SELECTs would be fragile.

`DB.pretend(callback)` instead opens a transaction, captures the SQL into a local sink, runs
the callback, and **rolls back** — statements execute against the connection but nothing
persists. It returns the captured log. The semantic difference (executed-then-discarded vs
never-executed) is documented; for previewing writes without committing them, the behavior
is equivalent and safe.

### ADR-005 § 12-03: `to_raw_sql` / `get_bindings` / `explain` on the builder

Status: Accepted

- `to_raw_sql()` returns SQL with bindings inlined — it reuses `to_sql()` (already compiles
  with `literal_binds=True`). Kept as a named method to match Laravel's `toRawSql`.
- `get_bindings()` returns the compiled statement's parameter values in order
  (`compiled.params.values()`), like Laravel's `getBindings`.
- `explain()` runs the dialect's plan command — `EXPLAIN QUERY PLAN` on SQLite, `EXPLAIN`
  elsewhere — against the inlined SQL and returns the plan rows as dicts.

---

## § 13 — Date/time, LIKE, and join helpers

**Originally**: ADR-038

Status: Accepted

Eloquent-parity increment (backlog `005`, stories S1, S5, S6). All build on the WHERE
predicate engine from ADR-005 § 5.

### ADR-005 § 13-01: Date/time WHERE helpers via `extract`

Status: Accepted

`where_year` / `where_month` / `where_day` / `where_date` / `where_time` (and `or_*` variants)
use SQLAlchemy's `extract(field, col)`, which compiles to native `EXTRACT` on PostgreSQL and
to `CAST(STRFTIME(...) AS INTEGER)` on SQLite — so they stay dialect-portable without per-
backend SQL. `where_date` / `where_time` compose the relevant parts (year+month+day,
hour+minute+second) rather than relying on `DATE()`/`TIME()`, which aren't uniformly available.
All values are bind parameters.

### ADR-005 § 13-02: LIKE + multi-column helpers

Status: Accepted

`where_like` / `where_not_like` (+`or_`) take a `case_sensitive` flag: `True` → `LIKE`, `False`
→ `ILIKE`. On PostgreSQL `LIKE` is case-sensitive and `ILIKE` is not. SQLite's `LIKE` is ASCII-
case-insensitive by design, so on SQLite the flag only changes the rendered SQL form, not the
result — documented, not worked around with GLOB. `where_all` (AND across columns),
`where_none` (NOR), and `or_where_any` round out the multi-column sugar. Patterns are always
bind parameters; literal `%`/`_` must be escaped by the caller.

### ADR-005 § 13-03: Join completeness

Status: Accepted

`cross_join` emits a join on `true()`. `join_on(target, closure)` exposes a fluent
`JoinClause`-style `on`/`or_on` ON builder. `right_join` is rewritten as
`target LEFT OUTER JOIN model` because SQLAlchemy has no native RIGHT JOIN — the standard,
result-equivalent transform that keeps the model's columns selected.

---

## § 14 — PostgreSQL FTS — Thin Helpers Over Searchable Mixin

**Originally**: ADR-039 · Date: 2026-05-23

### Decision

Add four thin helpers to `Blueprint` and `QueryBuilder` for PostgreSQL full-text search:
`tsvector()`, `gin_index()`, `where_full_text()`, `order_by_relevance()`.

### Context

Arvel's query builder and schema DSL had no FTS support. Developers needed to use `where_raw()` and `raw_column()`, which are verbose, non-discoverable, and provide no guardrails (e.g., no validation of `tsquery_fn`).

Two alternatives were considered:

- **Option A** (chosen): Four thin helpers, three files changed, no new abstractions.
- **Option B**: A `Searchable` mixin that auto-declares the column and exposes `Model.search()`.

### Rationale

Option B was rejected because vector population strategy (DB trigger, application-level update, or `to_tsvector()` computed column) varies per application and cannot be generalized at the framework level without opinionated choices that some apps won't want. Forcing a migration generation hook and a vector maintenance story into the framework before any real consumer exists violates YAGNI.

Option A delivers the full ergonomic improvement (typed, discoverable, safe bind params, allowlisted `tsquery_fn`) without coupling the framework to a particular population strategy.

### Consequences

- Consuming apps must maintain their own vector population logic (documented, not hidden).
- A `Searchable` mixin can be added later as a higher-level optional abstraction built on these primitives.
- `ts_rank_cd` and custom normalization weights remain accessible via `order_by_raw()`.

---

## § 15 — Closure-form Transaction Retry on Deadlock

**Originally**: ADR-040

Status: Accepted

Eloquent-parity increment (backlog `005`, Sprint B: story S12, partial). No HTTP or
schema surface — recorded as an ADR.

### ADR-005 § 15-01: Retry needs a closure form, separate from the CM `transaction()`

Status: Accepted

`DB.transaction()` is an `@asynccontextmanager` — the caller's `async with` body runs
exactly once, so a context manager can't re-run the body after a deadlock. Retry
requires the work to be a **callable** the facade can invoke again.

Rather than overload `transaction()` to return either a context manager or a coroutine
(which can't be typed cleanly under pyright strict), we add a distinct generic method:

```python
await DB.transactional(callback, attempts=3)   # callback: (AsyncSession) -> Awaitable[T]
```

Each attempt opens a fresh outermost `transaction()` (new session, real COMMIT/ROLLBACK),
so a rolled-back attempt leaves no state behind before the next try. The CM form is
unchanged for the common single-attempt case.

### ADR-005 § 15-02: Retry only on deadlock / serialization failures

Status: Accepted

`_is_retryable_db_error` returns true only for SQLAlchemy `OperationalError` /
`DBAPIError` whose driver error signals a deadlock or serialization conflict —
PostgreSQL SQLSTATE `40001` (serialization_failure) / `40P01` (deadlock_detected), or a
message token (`deadlock`, `serialization`, `could not serialize`, `database is locked`,
`lock wait timeout`). Everything else (integrity violations, app errors) propagates
immediately — retrying a logic error would just burn attempts and hide the bug.

### ADR-005 § 15-03: Imperative begin/commit/rollback via a frame stack

Status: Accepted (delivered WI-arvel-010)

Story S12 also lists imperative `begin_transaction`/`commit`/`rollback` with savepoint
interop. The earlier increment deferred it for lifecycle risk under the ContextVar session
model; this increment delivers it with an explicit frame stack instead of ad-hoc token
juggling.

`DB.begin_transaction()` pushes a `_TxnFrame` onto a context-local stack (`_IMPERATIVE_TXN`):

- **Outermost** (no active session): open a fresh session, `await session.begin()`, install
  it as the active session, and — if no outer after-commit queue exists — own a new one. The
  frame records the session/queue reset tokens.
- **Nested** (a session is already active, whether from a prior `begin_transaction()` or a
  surrounding `DB.transaction()` block): `await session.begin_nested()` opens a SAVEPOINT.
  The frame owns nothing.

`commit()` / `rollback()` pop the top frame. A savepoint frame commits (release) or rolls
back to the savepoint and returns. An outermost frame commits/rolls back the session, resets
the queue and session tokens it owns, closes the session, and — on commit only — fires the
after-commit callbacks. Calling `commit`/`rollback` with an empty stack raises.

Because nesting is decided by "is a session already active?", imperative savepoints compose
with the context-manager `transaction()` for free: a `begin_transaction()` inside an
`async with DB.transaction():` block is a savepoint on the context-managed session.

---

## § 16 — DB.transaction() uses begin_nested() for nesting

**Originally**: ADR-041 · Date: 2026-05-18

### Context

`DB.transaction()` needs to work both when called standalone (no active session) and when called
inside an HTTP request (active session exists from `DatabaseTransaction` middleware). Two options:
(a) always open a new connection, or (b) detect active session and use `begin_nested()` (savepoint).

### Decision

Detect active session via `get_active_session()`. If a session exists, use `begin_nested()` (SAVEPOINT).
If no session exists, open a new session from `async_sessionmaker`.

### Rationale

- A second connection in the same request means two separate transactions — reads in the outer transaction are not visible to the inner transaction and vice versa. That breaks correctness.
- Savepoints have correct nested semantics: inner rollback rolls back only to the savepoint; outer transaction can still commit.
- All supported databases (MySQL 8+, PostgreSQL, SQLite ≥ 3.25) support `SAVEPOINT` syntax.
- Compatible with HTTP middleware: the middleware session is reused, not replaced.

### Alternatives Rejected

- **Always open new connection**: Two-connection scenarios have visibility and consistency problems. Rejected.

---

## § 17 — QueryLoggingServiceProvider hooks sync_engine events

**Originally**: ADR-042 · Date: 2026-05-18

### Context

SQLAlchemy's `AsyncEngine` wraps a synchronous `Engine`. The event system (`event.listens_for`)
attaches to the synchronous layer. Two options for the attachment point: (a) `AsyncEngine` directly,
or (b) `AsyncEngine.sync_engine`.

### Decision

Attach to `engine.sync_engine`:

```python
engine: AsyncEngine = container.make(AsyncEngine)
_attach_logging(engine.sync_engine, slow_ms=...)
```

### Rationale

- SQLAlchemy's `before_cursor_execute` and `after_cursor_execute` events are synchronous events on the synchronous cursor — they fire regardless of the async wrapper.
- `AsyncEngine` does not expose the event interface directly for cursor-level hooks.
- `engine.sync_engine` is the canonical attachment point per SQLAlchemy documentation for `AsyncEngine` users wanting cursor-level events.

### Alternatives Rejected

- **Hook `AsyncEngine` directly**: The async engine does not expose `before_cursor_execute` / `after_cursor_execute`. Attaching would silently no-op.

---

## § 18 — Recursive CTE anchor derived from existing WHERE scope

**Originally**: ADR-043 · Date: 2026-05-18

### Context

A recursive CTE requires an "anchor" (the base case) and a "recursive step" (the join back to the
same table). The anchor must be specified. Two options: (a) require an explicit `root` parameter,
or (b) derive the anchor from the existing `.where()` scope on the builder.

### Decision

Derive the anchor from the existing `.where()` scope:

```python
## Anchor: WHERE parent_id IS NULL (already on the builder from .where())
Category.where(Category.parent_id == None).recursive("parent_id").all()

## Anchor: WHERE parent_id = :owner_id (set by has_many)
post.comments().recursive("parent_id").as_tree()
```

### Rationale

- When called after `has_many(Comment, foreign_key="parent_id")`, the FK WHERE is already on the builder. Adding `root=...` would duplicate it.
- When users write `Category.where(parent_id=None).recursive(...)`, the anchor is already expressed — no duplication.
- Fewer parameters = less cognitive load.

### Alternatives Rejected

- **Explicit `root` parameter**: `recursive(parent_key="parent_id", root=Category.parent_id.is_(None))` — redundant when used with `has_many`; users forget to add it when not using `has_many`.

---

## § 19 — Per-operation autocommit (PDO parity)

**Date**: 2026-06-11

### Context

The original design bound an `AsyncSession` to the request (or test) and required every ORM operation to run inside it. A single write flushed but didn't commit — only an explicit `DB.transaction()` or the request middleware committed. Outside a request you had to wrap even one `save()` in `DB.transaction()`, and operations with no active session raised `NoActiveSessionError`. That diverges from Laravel, where each query runs on a PDO connection in autocommit mode and a single write is atomic on its own.

### Decision

ORM terminals manage their own session through one primitive, `session_scope(*, commit)`:

- If a session is already bound (inside `DB.transaction()` or a `db_tx` request), reuse it and let that boundary own the COMMIT.
- Otherwise open a fresh session, run the operation, and — for writes — commit immediately.

Read terminals use `commit=False`; write and compound terminals use `commit=True`, applied via the `autocommit(write=...)` decorator (async generators wrap their body in `session_scope` directly). `DB.select/scalar/statement` and `TableQueryBuilder` route through the same primitive, which also fixes a latent bug where standalone `DB.statement()` flushed without committing.

### Consequences

- A single write is atomic without ceremony; `DB.transaction()` is reserved for grouping **multiple** writes. Nested terminals inside a transaction reuse the open session, so a compound op (e.g. `sync`) stays atomic.
- After a standalone autocommit, the ORM instance is detached. `save`/`delete`/`restore`/`force_delete` re-attach via `session.add()`/`merge()` before operating. The framework's session maker uses `expire_on_commit=False`, so a detached instance keeps its loaded attributes.
- A write scope that opens its own session also owns the after-commit queue, so model `after_commit` observers still fire on a standalone write.
- Operations with neither a bound session nor a configured default now raise `"DB not configured"` (from `session_maker_for`) instead of `NoActiveSessionError`.

### Alternatives Rejected

- **Keep the always-bound-session model**: forces `DB.transaction()` around every single write and breaks Laravel parity. Rejected.
- **Commit on every flush**: would break multi-write atomicity inside `DB.transaction()`. The reuse-or-open check in `session_scope` is what preserves it.

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-025 | 2026-05-18 | QB Write Ops Use SQLAlchemy Core, Not ORM Unit-of-Work | § 1 |
| ADR-026 | 2026-05-18 | TableQueryBuilder Is a Separate Class | § 2 |
| ADR-027 | 2026-05-18 | Collection[T] Is a list[T] Subclass | § 3 |
| ADR-029 | 2026-05-17 | Kwarg-shorthand `where(col=value)` binds parameters via `getattr`, never string SQL | § 4 |
| ADR-030 | — | WHERE Predicate Engine and Clause Polish | § 5 |
| ADR-031 | — | Query Builder Conditional Groups, `unless`/`tap`, and Efficient `exists` | § 6 |
| ADR-032 | — | Write-path completeness (insert_or_ignore / upsert count / truncate / insert_using / increment_each) | § 7 |
| ADR-033 | — | Subquery FROM / JOIN / SELECT | § 8 |
| ADR-034 | — | Framework Query Builder Critical Fixes | § 9 |
| ADR-035 | — | Streaming and Chunking Completeness | § 10 |
| ADR-036 | — | Pagination HTTP + JSON parity | § 11 |
| ADR-037 | — | Debugging and query-log parity | § 12 |
| ADR-038 | — | Date/time, LIKE, and join helpers | § 13 |
| ADR-039 | 2026-05-23 | PostgreSQL FTS — Thin Helpers Over Searchable Mixin | § 14 |
| ADR-040 | — | Closure-form Transaction Retry on Deadlock | § 15 |
| ADR-041 | 2026-05-18 | DB.transaction() uses begin_nested() for nesting | § 16 |
| ADR-042 | 2026-05-18 | QueryLoggingServiceProvider hooks sync_engine events | § 17 |
| ADR-043 | 2026-05-18 | Recursive CTE anchor derived from existing WHERE scope | § 18 |
