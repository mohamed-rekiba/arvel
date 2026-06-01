# ADR-031: Query Builder Conditional Groups, `unless`/`tap`, and Efficient `exists`

Status: Accepted

Eloquent-parity increment (backlog `005`, Sprint A: stories S2, S4, S7). No HTTP or
schema surface — recorded as an ADR, not a SAD/OpenAPI spec.

## ADR-031-01: Nested `WHERE` groups via a callback that returns a builder

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

## ADR-031-02: `unless` is `when` with a negated condition; `tap` is side-effect only

Status: Accepted

`unless(cond, cb, otherwise=None)` delegates to `when(not cond, ...)` — one
implementation, no divergence. `tap(cb)` hands a clone to the callback for
inspection/logging and returns that clone unchanged; the callback's return value is
ignored, matching Laravel's `tap` contract (side effects, not transformation).

## ADR-031-03: `exists` issues `SELECT EXISTS(...)`, not `COUNT(*) > 0`

Status: Accepted

The old `exists()` ran `SELECT count(*) FROM (subquery)` then compared to zero —
the database materializes and counts every matching row. We now emit
`SELECT EXISTS (SELECT 1 FROM ... WHERE ... LIMIT 1)`, letting the planner
short-circuit on the first hit. Global scopes still apply (built on
`apply_global_scopes()`). `doesnt_exist()` is the negation.
