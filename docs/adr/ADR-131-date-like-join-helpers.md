# ADR-131: Date/time, LIKE, and join helpers

Status: Accepted

Eloquent-parity increment (backlog `005`, stories S1, S5, S6). All build on the WHERE
predicate engine from ADR-130.

## ADR-131-01: Date/time WHERE helpers via `extract`

Status: Accepted

`where_year` / `where_month` / `where_day` / `where_date` / `where_time` (and `or_*` variants)
use SQLAlchemy's `extract(field, col)`, which compiles to native `EXTRACT` on PostgreSQL and
to `CAST(STRFTIME(...) AS INTEGER)` on SQLite — so they stay dialect-portable without per-
backend SQL. `where_date` / `where_time` compose the relevant parts (year+month+day,
hour+minute+second) rather than relying on `DATE()`/`TIME()`, which aren't uniformly available.
All values are bind parameters.

## ADR-131-02: LIKE + multi-column helpers

Status: Accepted

`where_like` / `where_not_like` (+`or_`) take a `case_sensitive` flag: `True` → `LIKE`, `False`
→ `ILIKE`. On PostgreSQL `LIKE` is case-sensitive and `ILIKE` is not. SQLite's `LIKE` is ASCII-
case-insensitive by design, so on SQLite the flag only changes the rendered SQL form, not the
result — documented, not worked around with GLOB. `where_all` (AND across columns),
`where_none` (NOR), and `or_where_any` round out the multi-column sugar. Patterns are always
bind parameters; literal `%`/`_` must be escaped by the caller.

## ADR-131-03: Join completeness

Status: Accepted

`cross_join` emits a join on `true()`. `join_on(target, closure)` exposes a fluent
`JoinClause`-style `on`/`or_on` ON builder. `right_join` is rewritten as
`target LEFT OUTER JOIN model` because SQLAlchemy has no native RIGHT JOIN — the standard,
result-equivalent transform that keeps the model's columns selected.
