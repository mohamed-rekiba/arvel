# ADR-154: pivot ergonomics for BelongsToMany

Status: Accepted (delivered WI-arvel-035)

Epic 007 Story 10. Adds Eloquent's many-to-many pivot conveniences to `BelongsToMany`:
`with_pivot`, `with_timestamps`, the `as` accessor name, `order_by_pivot`,
`where_pivot_in`/`_not_in`/`_between`/`_null`, and `create`/`save` on the relation.

## Context

`BelongsToMany` already had `attach`/`detach`/`sync`/`toggle`/`pivot`/`where_pivot`. What was missing
is the ergonomic layer Eloquent gives you when a pivot row carries data: surfacing extra pivot columns
on the related model, auto-maintaining pivot timestamps, filtering/ordering by pivot columns, and
persisting-then-attaching in one call.

## ADR-154-01: `PivotConfig` + fluent configuration

Status: Accepted

A frozen `PivotConfig(columns, timestamps, created_at, updated_at, accessor)` carries the per-relation
settings. The descriptor exposes fluent builders applied at class definition, mirroring Eloquent's
chained relation definition:

```python
tags = (
    BelongsToMany(Tag, table=post_tags, foreign_key="post_id", related_foreign_key="tag_id")
    .with_pivot("role", "priority")
    .with_timestamps()
    .as_("membership")
)
```

Each builder returns the descriptor (one descriptor per attribute, so mutation is safe) and the config
is handed to every accessor built by `__get__`.

## ADR-154-02: `with_pivot` hydration

Status: Accepted

When pivot columns are configured, the accessor's read path (`all`, `_iter_related`, and every
`where_pivot_*`/`order_by_pivot`) selects those columns alongside the related model and attaches a
`SimpleNamespace` of them onto each row under the accessor name (default `pivot`, overridable via
`as_`). So `tag.membership.role` reads the pivot column. The eager-cache fast path is preserved — `all`
returns the cached collection without re-querying when the relation was eager-loaded.

## ADR-154-03: `with_timestamps`

Status: Accepted

`attach` fills `created_at` + `updated_at` and `update_pivot` bumps `updated_at` (both via
`datetime.now(UTC)`, only when not already supplied). `sync`/`sync_without_detaching` inherit this
through `attach`/`update_pivot`. Column names are configurable through `with_timestamps(created_at,
updated_at)`.

## ADR-154-04: pivot filters and ordering

Status: Accepted

`order_by_pivot(column, direction)`, `where_pivot_in`, `where_pivot_not_in`, `where_pivot_between`, and
`where_pivot_null(column, negate=...)` each build the join query with the owner predicate plus their
pivot predicate and return the related rows (pivot-hydrated). These are terminal `async` methods
returning `list[T]` rather than a chainable relation-query builder — the simplest surface that satisfies
each filter independently.

## ADR-154-05: `create` / `save` on the relation

Status: Accepted

```python
tag = await post.tags.create(pivot={"role": "owner"}, name="ops")  # create related + attach
await post.tags.save(existing_tag, pivot={"priority": 7})          # persist if needed + attach
```

`create` builds the related model then attaches it with optional pivot data; `save` persists an
unsaved instance (PK is null) before attaching.

## ADR-154-06: deferred — custom `Pivot` model via `using`

Status: Deferred

Eloquent's `using(PivotModel)` (a typed pivot model with its own casts/accessors) is intentionally left
out of this increment. The `SimpleNamespace` pivot accessor covers the read use case the acceptance
criteria require; a full typed pivot model is a larger abstraction and will be tracked separately.
