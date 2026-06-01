# ADR-076: relation defaults, eager control, and cascade save

Status: Accepted (delivered WI-arvel-036)

Epic 007 Story 11. Adds the last batch of relation ergonomics from Eloquent:
`with_default` on `BelongsTo`, `$touches`-style parent timestamp propagation,
`without()`/`with_only()` eager control, and `push()`.

## Context

`belongs_to(...)` returns a builder; when the FK is null it had no WHERE filter at all, so
`.first()` could match an arbitrary row. Eager loads were applied directly to `_stmt` inside
`with_()`, which made them impossible to drop or replace later. And there was no cascade-save or
parent-touch.

## ADR-076-01: `BelongsTo.with_default`

Status: Accepted

`BelongsTo` tracks whether the owner's FK was present (`fk_present`) and a `_default` spec.
`first()` returns the default when the FK is null or no row matched:

```python
author = await post.author().with_default().first()                 # empty instance
author = await post.author().with_default({"name": "Guest"}).first() # attributes
author = await post.author().with_default(fill).first()              # (instance, owner) callback
```

A real matched parent always wins over the default. Without `with_default`, a null FK returns
`None` (and no longer risks matching an arbitrary row, since `fk_present=False` short-circuits).

## ADR-076-02: deferred eager loads + `without` / `with_only`

Status: Accepted

`with_()` no longer mutates `_stmt`. It records each sync (selectinload) request onto
`_eager_loads` (and async/pivot requests onto `_async_eager` as before). The loader options are
materialised in `apply_global_scopes`, so they can be edited between `with_()` and execution:

- `without("posts")` drops a pending eager load by path.
- `with_only("posts")` clears all pending loads, then registers exactly the given ones.

The relation head is still validated eagerly (`_validate_eager_head`) so an unknown relation
raises `UnknownRelationError` at call time, matching the prior fail-fast behaviour.

## ADR-076-03: `$touches` and `push`

Status: Accepted

`__touches__` is a tuple of parent relation-accessor method names. After a successful `save()`,
`_touch_parents` resolves each accessor, fetches the parent, and calls `parent.touch()` — bumping
its `UPDATED_AT`. Empty by default, so it's zero-cost for models that don't opt in.

`push()` saves the model, then walks every loaded relationship in the identity map (skipping
unloaded ones) and calls `push()` on each related instance, cascading pending edits downward.

## ADR-076-04: deferred — eager column selection

Status: Deferred

Eloquent's `with("posts:id,title")` column pruning is left out. Selectin loaders hydrate full rows
into the identity map; partial column loads interact poorly with later attribute access and
expiry. Tracked separately rather than shipped half-working.
