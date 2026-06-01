# ADR-030: WHERE Predicate Engine and Clause Polish

Status: Accepted

Eloquent-parity increment (backlog `005`, story S13). Foundational change to how the
query builder accumulates `WHERE`, plus the remaining clause-variant bundle.

## ADR-030-01: WHERE lives in a builder predicate, not on the `Select`

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

## ADR-030-02: `or_where` ORs onto the whole chain, with explicit grouping

Status: Accepted

`where(a).or_where(b).where(c)` produces `(a OR b) AND c` — explicit, parenthesized grouping.
This differs from Laravel's flat, precedence-driven `a OR b AND c` (= `a OR (b AND c)`), a
known footgun. Arvel chooses explicit grouping deliberately: it's predictable and keeps
global scopes (soft deletes, tenancy) ANDed around the entire user predicate. New `or_where_in`
/ `or_where_not_in` / `or_where_null` / `or_where_not_null` / `or_where_raw` / `or_where_between`
follow the same rule.

## ADR-030-03: Clause polish bundle

Status: Accepted

Added the remaining Laravel clause variants: `order_by_desc`, `reorder` (drop then optionally
re-set ORDER BY via `Select.order_by(None)`), `in_random_order` (`random()`), `group_by_raw`,
operator-form `having("total", ">", 5)` plus `having_null` / `having_between`, `pluck(value,
key)` returning a dict, `count(column)` (COUNT of non-null values), and `sum()` returning `0`
on an empty set (Laravel parity — the prior `None` behaviour was changed).
