# ADR-151: polymorphic existence queries (where_has_morph / has_morph)

Status: Accepted (delivered WI-arvel-032)

Epic 007 Story 7. Adds Laravel's `whereHasMorph` / `hasMorph` / `whereMorphRelation` — filter a
`MorphTo` against several concrete target types at once.

## Context

`where_has` already builds an `EXISTS` subquery for a single relation. A `MorphTo` (e.g.
`Comment.commentable → Post | Video`) has no single related table — the target depends on the row's
`{name}_type` token. So existence has to fan out: one branch per candidate type, each pinned to that
type's morph alias, OR'd together.

## ADR-151-01: `where_has_morph(relation, types, constraint=None)`

Status: Accepted

```python
Comment.query().where_has_morph("commentable", [Post, Video])
Comment.query().where_has_morph(
    "commentable", [Post], lambda q, type_model: q.where(Post.published == True)
)
```

For each `type_model` it builds `AND(commentable_type == alias, EXISTS(SELECT type WHERE type.pk ==
commentable_id [AND constraint]))` and OR's the branches. The alias comes from `get_morph_alias`, so a
registered `morph_map({"post": Post})` is honoured automatically — the predicate compares against
`"post"`, matching what `associate()` stored. The constraint closure gets `(query, type_model)` so it
can branch on the concrete type, exactly like Eloquent's `($query, $type)`. Each branch runs through
`apply_global_scopes`, so soft-deleted parents don't count. Empty `types` → matches nothing
(`false()`), no SQL surprise.

## ADR-151-02: `has_morph(relation, types, operator, count, constraint=None)`

Status: Accepted

Count-based variant. Per type it builds a correlated `COUNT` scalar subquery (mirroring
`_morph_child_count_subquery`), applies the operator/count, pins the type alias, and OR's the branches.
A `MorphTo` resolves to at most one parent, so the practical use is `>= 1`, but the general operator
form is there for parity.

## ADR-151-03: `where_morph_relation(relation, types, column, value)`

Status: Accepted

Thin sugar over `where_has_morph` — the polymorphic sibling of `where_relation`:

```python
Comment.query().where_morph_relation("commentable", [Post], "title", "keep")
```

## ADR-151-04: Scope and guards

Status: Accepted

All three resolve the relation via `_morph_to_name` and raise `UnknownRelationError` unless it's a
`MorphTo`. The closure type is a module alias `_MorphConstraint = Callable[[QueryBuilder, type], QueryBuilder]`.
These methods live on the *child* model's query (the side that owns the `{name}_type` / `{name}_id`
columns) — the owner side already has `where_has` over `MorphOne`/`MorphMany`.
