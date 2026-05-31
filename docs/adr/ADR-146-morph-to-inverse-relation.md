# ADR-146: MorphTo inverse relation

Status: Accepted (delivered WI-arvel-027)

Epic 007 Story 2. Builds on the morph map (ADR-145). Adds the child→parent side of polymorphism —
`comment.commentable`.

## ADR-146-01: `MorphTo` descriptor + accessor

Status: Accepted

`MorphTo(name="commentable")` is a class-level descriptor on the child model. Unlike `MorphOne`/
`MorphMany` it has no fixed related class — the parent type varies per row. The bound
`MorphToAccessor` is awaitable: `await comment.commentable` reads the stored `{name}_type` token,
resolves it to a class via `resolve_morph_class` (morph map, then registry fallback), and loads the
parent by `{name}_id`. Null discriminators return `None` instead of querying.

## ADR-146-02: `associate` / `dissociate`

Status: Accepted

`associate(parent)` sets `{name}_type` (via `get_morph_alias`) and `{name}_id` (`parent.get_key()`)
together, and primes the eager cache so an immediate `await child.<rel>` returns the associated
instance without a round-trip. `dissociate()` nulls both columns and clears the cache. Both are
synchronous attribute mutations (the caller saves the child) and return the child for chaining —
matching Eloquent.

## ADR-146-03: Batched eager loading grouped by type

Status: Accepted

`MorphTo` plugs into the existing async eager engine. `with_("commentable")` registers an async
spec; `batch_load_morph_to` groups children by their `{name}_type` token and runs **one query per
distinct type** (`WHERE pk IN (...)`), then stores each parent on its child through the per-instance
eager cache (`set_eager_relation`). Accessing `child.commentable` after eager loading reads the
cache — no N+1.

The query builder gained a `morph_to` relation kind: `_resolve_relation` returns it,
`_is_async_relation` routes it to the async path, and `_load_async_relation_path` dispatches to
`batch_load_morph_to`. A `morphTo` is a **leaf** in eager paths — nested paths through it (e.g.
`commentable.author`) aren't resolvable statically because the parent type varies per row. Laravel's
`morphWith` covers that case and is out of scope here.

## ADR-146-04: Why store the morph name (not the descriptor) on `_RelationTarget`

Status: Accepted

`_RelationTarget` carries `morph_name: str` rather than the `MorphTo[T]` descriptor. The loader only
needs the base name, and a plain `str` keeps the resolved-relation dataclass free of an unbound
generic that the strict type checkers flag as partially unknown.
