# ADR-147: MorphOne/MorphMany query + eager integration

Status: Accepted (delivered WI-arvel-028)

Epic 007 Story 3. Makes `MorphOne`/`MorphMany` first-class query relations so they participate in
`with_()`, `where_has`/`has`/`doesnt_have`, `with_count`, and `Model.load()` — not just lazy
accessor reads.

## ADR-147-01: `morph_child` relation kind

Status: Accepted

`_resolve_relation` now recognises `MorphOne`/`MorphMany` descriptors and returns a `morph_child`
target carrying a `MorphChildLink` (related model, morph base name, owner alias, and a `single` flag
for one-vs-many cardinality). The link is built from `descriptor.link_spec(get_morph_alias(model))`
so the owner token honours the morph map (ADR-145).

## ADR-147-02: Existence + count subqueries

Status: Accepted

`where_has`/`has`/`doesnt_have` and `with_count` build their subqueries against the child table with
the morph predicate pair:

```sql
... WHERE child.{name}_id = parent.pk AND child.{name}_type = '<owner-alias>'
```

Both honour the child model's global scopes (soft deletes), matching the pivot relations. The count
branch was extracted to `_morph_child_count_subquery` to keep `_count_subquery` under the complexity
gate.

## ADR-147-03: Batched eager loading

Status: Accepted

`with_("comments")` registers the relation on the async eager path (`_is_async_relation` now returns
True for `morph_child`). `batch_load_morph_children` runs a single
`WHERE {name}_type = alias AND {name}_id IN (parent_pks)` (+ any constraint-closure WHERE), groups
rows back to each parent by `{name}_id`, and stores them in the per-instance eager cache. The
`MorphOne`/`MorphMany` accessors now read that cache first (returning the single first row for
`MorphOne`, the list for `MorphMany`), so iterating after eager load is N+1-free. Nested paths
(`comments.author`) recurse through the normal async loader.

## ADR-147-04: `Model.load()` routes async relations

Status: Accepted

`Model.load(*relations)` splits its arguments: SQLAlchemy relationships still go through a
`selectinload` re-query, while async descriptor relations (BelongsToMany / MorphToMany / MorphOne /
MorphMany) batch-load into the eager cache via the new public `load_async_relation_path`. Those two
query helpers (`is_async_relation`, `load_async_relation_path`) were promoted to public wrappers so
`model.py` doesn't reach into query.py privates.
