# ADR-148: morphedByMany — inverse polymorphic many-to-many

Status: Accepted (delivered WI-arvel-029)

Epic 007 Story 4. Adds the inverse side of `MorphToMany`: the relation declared on the model the
pivot's `{name}_type`/`{name}_id` point at — e.g. `tag.posts` / `tag.videos` over one `taggables`
pivot. Mirrors Laravel's `morphedByMany`.

## ADR-148-01: `MorphedByMany` descriptor + accessor

Status: Accepted

`MorphToMany` (forward) filters the pivot by the *owner's* type and joins the related table by its
own FK column. `MorphedByMany` (inverse) flips that:

- the morph discriminator pins the **related** model's alias (`{name}_type == get_morph_alias(related)`)
- the owner's PK lives in a plain pivot FK column (`related_key`, e.g. `tag_id`)
- the related rows join back through `{name}_id`, string-cast since that column is VARCHAR:
  `pivot.{name}_id == CAST(related.pk AS VARCHAR)`

The accessor exposes `all()` / async iteration, `attach`/`detach`/`toggle`/`sync`, mirroring the
forward accessor's write semantics (idempotent attach, string-cast id on write).

## ADR-148-02: Lazy related model

Status: Accepted

Inverse relations almost always point at a model defined later in the same module (`Tag` declares
`posts` before `Post` exists). So `MorphedByMany` accepts either a class or a `lambda: Model` thunk
and resolves it lazily on first access (cached). The forward `MorphToMany` keeps its eager
`type[T]` argument — the related model is defined first there, so no thunk is needed.

## ADR-148-03: Query + eager integration (`mbm` kind)

Status: Accepted

`_resolve_relation` recognises `MorphedByMany` and returns a `mbm` target carrying a
`MorphedByManyLink` (table, related model, type/id columns, owner FK column, related alias). The new
kind is wired into the same paths as the other pivot relations:

- `with_("posts")` → `_is_async_relation` returns True; `_batch_load_async` runs one
  `WHERE {name}_type = alias AND {owner_fk} IN (owner_pks)` join, groups rows by the owner FK value,
  and stores each owner's slice in the eager cache (N+1-free, verified by a SELECT counter).
- `where_has`/`has`/`doesnt_have` → `_pivot_exists_select` builds the EXISTS subquery.
- `with_count("posts")` → `_mbm_count_subquery` adds the per-owner count column.
- `Model.load("posts")` → routes through the public `load_async_relation_path`.

`_exists_subquery` and `_count_subquery` grew past the complexity gate with the extra kind, so both
were refactored into thin dispatchers over per-kind helpers (`_pivot_exists_select`,
`_sa_count_subquery` / `_mtm_count_subquery` / `_btm_count_subquery` / `_mbm_count_subquery`).
