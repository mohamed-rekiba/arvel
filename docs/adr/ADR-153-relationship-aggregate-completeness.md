# ADR-153: relationship aggregate completeness

Status: Accepted (delivered WI-arvel-034)

Epic 007 Story 9. Rounds out relation aggregates to match Eloquent's `withCount`/`withSum`/`withAvg`/
`withMin`/`withMax`/`withExists` plus the instance-level `loadCount`/`loadSum`/`loadAggregate`/
`loadExists`.

## Context

Arvel had `with_count` (pivot-aware) and bespoke `with_sum`/`with_max` that only handled plain SQLA
relationships — no avg/min, no exists, no pivot sum, no aliasing, no constraint closures, and no
after-the-fact instance loaders. Each method also re-derived its own correlated subquery. Since every
aggregate reduces to "scope the relation's rows, then apply an aggregate function", they now share one
builder.

## ADR-153-01: `_aggregate_column` — one builder for every aggregate

Status: Accepted

`_aggregate_column(model, target, agg, col, constraint)` resolves the relation via
`_relation_exists_select` (so it's **pivot-aware** — `BelongsToMany`/`MorphToMany`/`MorphedByMany` join
through the pivot automatically), applies the optional constraint, runs `apply_global_scopes` (so
soft-deleted related rows never count), then:

- `count` → reuses the proven `_count_subquery` (no constraint) or `_constrained_count_subquery`.
- `exists` → `select.exists()` (boolean).
- `sum`/`avg`/`min`/`max` → `with_only_columns(func.<agg>(related.col)).scalar_subquery()`.

## ADR-153-02: `with_aggregate` and the named wrappers

Status: Accepted

```python
Post.query().with_avg("comments", "rating")
Post.query().with_min("comments", "rating")
Post.query().with_exists("comments")
Post.query().with_sum("tags", "weight")          # pivot-aware
```

`with_count`/`with_sum`/`with_avg`/`with_min`/`with_max`/`with_exists` all delegate to
`with_aggregate(relation, agg, col, alias, constraint)`. The result is hydrated onto each instance under
its column label by the existing `__with_agg__` result path.

## ADR-153-03: aliasing and constraint closures

Status: Accepted

The relation string accepts an `" as <alias>"` suffix (`with_count("comments as comment_total")`), and
an explicit `alias=` kwarg wins over that. A `constraint=` closure filters the aggregated rows:

```python
Post.query().with_count("comments", constraint=lambda q: q.where(Comment.spam == False))
Post.query().with_sum("comments", "rating", alias="ham_score",
                      constraint=lambda q: q.where(Comment.spam == False))
```

Default labels match Eloquent: `{rel}_count`, `{rel}_exists`, `{rel}_{agg}_{col}`.

## ADR-153-04: instance loaders

Status: Accepted

`load_aggregate_for(instance, relation, agg, col, alias, constraint)` computes one aggregate for a
single already-fetched instance: `SELECT <agg> ... FROM model WHERE pk = instance.key`, then caches the
scalar on the instance under the label. The `Model` exposes `load_count`, `load_sum`, `load_exists`, and
the general `load_aggregate` (covers avg/min/max):

```python
await post.load_count("comments")          # post.comments_count
await post.load_sum("comments", "rating")  # post.comments_sum_rating
await post.load_aggregate("comments", "avg", "rating")
await post.load_exists("comments")         # post.comments_exists
```

The cache write uses `object.__setattr__` under `suppress(AttributeError, TypeError)` so read-only
descriptors or frozen dataclasses don't break the call — same contract as the eager `with_*` path.
