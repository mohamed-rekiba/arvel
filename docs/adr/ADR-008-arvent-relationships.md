# ADR-008 — Arvent — Relationships & Polymorphism

**Status**: Accepted
**Date**: original decisions 2026-05-17 – 2026-05-18; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: HasMany method pattern, BelongsToMany upsert, soft-delete global scope, morph-map foundation, MorphTo inverse, morph child query/eager, morphedByMany, has-one-of-many, chaperone, polymorphic existence queries, relation querying, aggregate completeness, pivot ergonomics, relation defaults & eager-load control.

## Why this is one ADR

Arvent's relationship story is one polymorphic graph — has-many, belongs-to-many, morph-to, morph-many, morphed-by-many — and these fourteen ADRs evolve that graph one descriptor at a time.

---

## § 1 — HasMany uses method pattern, not class-attribute descriptor

**Originally**: ADR-063 · Date: 2026-05-18

### Context

Simple FK relations (`HasMany`, `HasOne`, `BelongsTo`) need to return a `QueryBuilder[T]`
so users can chain `.where()`, `.order_by()`, `.recursive()`, etc. Two patterns were considered:
(1) class-attribute descriptors like `BelongsToMany`, and (2) instance methods returning a builder.

### Decision

Use **instance methods**:

```python
class Post(Model):
    def comments(self) -> HasMany[Comment]:
        return self.has_many(Comment)
```

### Rationale

- No `__get__` / `__set_name__` overload complexity
- Arbitrary constraints can be applied at definition time (e.g., `self.has_many(Comment).where(approved=True)`)
- Return type is explicit and statically checkable: `HasMany[Comment]` (a `QueryBuilder[T]` subclass)
- Consistent with how users write scopes — just an instance method returning a builder
- `BelongsToMany` uses descriptors for historical reasons (WI-003); new relations don't need to match that

### Alternatives Rejected

- **Class-attribute descriptor**: Requires `__get__` to receive `self`; complicates applying initial WHERE scopes; harder to type-check the generic parameter.

---

## § 2 — BelongsToMany Pivot Attach: UPSERT on PK Conflict

**Originally**: ADR-064 · Date: 2026-05-17

### Context

`PivotProxy.attach(id_or_model, **pivot)` needs to handle the case where the pivot row already exists. Two options:

1. **Hard INSERT — fail on conflict**: caller must call `detach()` first; idempotent calls are not safe
2. **UPSERT (INSERT … ON CONFLICT DO UPDATE)**: idempotent; pivot columns are updated on re-attach

### Decision

Use **UPSERT** (`INSERT … ON CONFLICT (fk, rfk) DO UPDATE SET …pivot_cols`).

### Rationale

- Idempotent calls are a common pattern — `sync()` calls `attach()` for each ID; hard-INSERT would require a prior `detach()` dance
- Matches Laravel's `attach()` behaviour when called on an already-attached ID with `touch=true`
- SQLAlchemy's `insert().prefix_with("OR REPLACE")` (SQLite) and `on_conflict_do_update()` (PostgreSQL) cover both supported backends without raw SQL
- No data loss risk: pivot columns are updated to the latest values on conflict

### Consequences

- `PivotProxy.attach()` never raises `IntegrityError` for duplicate PK — callers cannot distinguish "new attach" from "update attach" without inspecting the result
- `PivotProxy.attach()` returns a `bool` — `True` if the row was newly inserted, `False` if updated — via `rowcount` heuristic
- Callers that need a "fail if already attached" semantic must call `PivotProxy.exists(id)` first (explicit over implicit)
- `sync()` uses UPSERT + DELETE-where-not-in — single round trip for PostgreSQL using `executemany` + UPSERT + `DELETE WHERE id NOT IN (...)`

---

## § 3 — Soft-Delete Filter as GlobalScope

**Originally**: ADR-065 · Date: 2026-05-18

### Decision

`SoftDeletes.__init_subclass__` registers a `GlobalScope` named `"soft_delete"` on the model class. This scope appends `WHERE deleted_at IS NULL` to every SELECT query on the model.

### Context

The current implementation only gates instance-level `delete()`/`restore()`. It does NOT filter SELECTs, so `User.all()` returns soft-deleted rows — broken behavior.

### Options

**A. Override `query()` in `SoftDeletes`** — manually add the WHERE clause in a classmethod override. Brittle: any new QB entry point would need the same override.

**B. SQLAlchemy mapper `with_loader_criteria`** — register a criteria function at the mapper level. Works but couples the soft-delete to SQLAlchemy internals more deeply than necessary.

**C. GlobalScope mechanism** ← chosen. The existing `GlobalScope` machinery in arvel is the right abstraction. `with_trashed()` becomes `without_global_scope("soft_delete")` — the same pattern Laravel uses.

### Consequences

- All QB SELECT paths automatically exclude soft-deleted rows for `SoftDeletes` models
- `with_trashed()` and `only_trashed()` work uniformly across all QB entry points
- The scope name `"soft_delete"` is a string constant — import from `arvel.database.scope`

---

### Merged: Soft-delete upsert + bulk restore (was ADR-008 § 3)

Status: Accepted (delivered WI-arvel-022)

Eloquent-parity increment (backlog `006`, story S10). Closes the restore-if-trashed-else-create
gap and adds bulk restore + force-destroy. No schema change.

### ADR-008 § 3-01: `restore_or_create` searches with trashed, restores in place

Status: Accepted

`restore_or_create(attributes, values)` runs `with_trashed().where(**attributes).first()`. If a
row exists it restores it when `trashed()`, then returns it — so a soft-deleted row is reused, not
duplicated (the bug the story targets). If none exists it creates with `{**attributes, **values}`,
matching `first_or_create`'s merge. `create_or_restore` is a thin alias; Eloquent ships both names
and people reach for either.

The search deliberately bypasses the soft-delete global scope — otherwise a trashed match would be
invisible and you'd create a duplicate, defeating the point.

### ADR-008 § 3-02: Bulk `QueryBuilder.restore()` mirrors bulk `delete()`

Status: Accepted

`restore()` issues a single `UPDATE ... SET deleted_at = NULL` over the current WHERE, the inverse
of the soft-delete branch in `delete()`. It bumps `updated_at` via the same `_touch_updated_at`
helper. Like every bulk write it bypasses per-row model events (Eloquent parity) — callers needing
per-row `restored` hooks restore instances individually.

Because the default soft-delete scope hides trashed rows, `query().restore()` alone matches
nothing. Callers pair it with `only_trashed()` (or `with_trashed().where(...)`), which flips/strips
the scope so the UPDATE targets the trashed rows. Raises `AttributeError` on models without
`SoftDeletes`, consistent with `with_trashed()`/`only_trashed()`.

### ADR-008 § 3-03: `trashed()` instance helper

Status: Accepted

`trashed()` returns whether the soft-delete column is set, `False` for models without
`SoftDeletes`. Reused by `restore_or_create` to decide whether a found row needs restoring.

### ADR-008 § 3-04: `force_destroy(*ids)` hard-deletes by primary key

Status: Accepted

`force_destroy` accepts varargs or a single iterable (`force_destroy(1, 2)` or
`force_destroy([1, 2])`) and routes through `query().where_in(pk, ids).force_delete()`. Since
`force_delete()` already strips the soft-delete scope, trashed rows are included. Returns the row
count. The primary-key attribute is resolved from the mapper, so composite-PK models would need a
different shape — single-PK is the supported case, the overwhelming default.

---

## § 4 — Morph map foundation

**Originally**: ADR-066

Status: Accepted (delivered WI-arvel-025+1 / WI-arvel-026)

Supersedes the unqualified-class-name default of ADR-008 § 4 for the polymorphic `{name}_type` token.
First story of Epic 007 (relationship parity).

### Context

ADR-008 § 4 stored the owner's *unqualified class name* (`"Post"`) in the morph discriminator column.
That token is tied to the class name and its position in the import graph — rename `Post`, move it
to another package, and every stored `{name}_type` value silently stops resolving. Laravel solved
this with `Relation::morphMap()`: an explicit, stable alias per model.

### ADR-008 § 4-01: Process-global morph map

Status: Accepted

`morph_map({"post": Post, "video": Video})` registers alias→class entries (merge by default;
`merge=False` replaces). Called bare, `morph_map()` returns the current map. State lives in a single
module-level `_MorphState` instance mutated in place (no `global` rebinds, keeps `ruff PLW0603`
happy). It's process-global, matching Laravel — register once at boot. Tests reset it via
`reset_morph_map()` wired into the autouse `reset_global_state` fixture.

### ADR-008 § 4-02: Token resolution, both directions

Status: Accepted

- `get_morph_alias(cls)` (write side): the mapped alias if `cls` is in the map, else the short class
  name (the ADR-008 § 4 default — so unmapped apps behave exactly as before).
- `resolve_morph_class(alias)` (read side, for MorphTo in Story 2): the mapped class, else a fallback
  scan of `Model.registry.mappers` by short class name. Raises `MorphMapError` when nothing matches.
- `Model.get_morph_class()` is the public classmethod form of `get_morph_alias(cls)`.

All existing morph write/read paths (`MorphOne`/`MorphMany` create + query, `MorphToMany` pivot
ops, the query-builder morph-existence subquery) now route the token through `get_morph_alias` so a
registered alias is used consistently on both write and read. Unmapped models keep storing the short
name, so `test_morph.py` / `test_morph_to_many.py` pass unchanged.

### ADR-008 § 4-03: Strict mode

Status: Accepted

`require_morph_map(True)` flips strict mode: `get_morph_alias` (and therefore any polymorphic write)
raises `MorphMapError` for an unmapped model instead of falling back to the class name. Apps that
want refactor-proof tokens enforced everywhere turn this on at boot. Off by default.

### Migration note

Apps already storing short class names need no migration — that's still the unmapped default. Apps
adopting aliases should backfill existing `{name}_type` values from the old class name to the new
alias in a one-off migration, then call `morph_map(...)` (and optionally `require_morph_map()`) at
boot before any polymorphic write.

---

### Merged: Morph Discriminator: Short Class Name (was ADR-008 § 4)

**Date**: 2026-05-17
**Status**: Accepted
**Deciders**: Solution Architect

---

### Context

`MorphOne` / `MorphMany` relations require a discriminator column (`{rel}_type`) that identifies the owning model. Two conventions exist:

1. **Fully-qualified class name (FQCN)**: `"myapp.articles.Article"` — unique across packages but couples the DB to module paths
2. **Short class name**: `"Article"` — matches Laravel's convention; simpler but theoretically ambiguous if two classes share a name

### Decision

Use **short class name** (e.g., `"Article"`) for the `{rel}_type` discriminator column.

### Rationale

- Matches Laravel Eloquent's convention exactly — contributors familiar with Laravel have zero learning curve
- Module paths are refactoring targets; baking an FQCN into a DB column means a rename breaks existing rows
- Arvel apps are modular monoliths (constitution Article III §1) where short name conflicts are extremely rare and linted at boot time
- At `Application` boot, `_loader` validates that no two registered morph-eligible models share the same short class name — raises `ConfigurationError` if they do

### Consequences

- Boot-time validation required: `arvel.console._bootstrap` (and `ApplicationBuilder`) must scan registered models for short-name collisions
- Migration docs must note that renaming a model class requires a data migration to update `{rel}_type` column values
- Tooling (`make:migration`) should warn if it detects a model rename touching a morphable model

---

## § 5 — MorphTo inverse relation

**Originally**: ADR-067

Status: Accepted (delivered WI-arvel-027)

Epic 007 Story 2. Builds on the morph map (ADR-008 § 4). Adds the child→parent side of polymorphism —
`comment.commentable`.

### ADR-008 § 5-01: `MorphTo` descriptor + accessor

Status: Accepted

`MorphTo(name="commentable")` is a class-level descriptor on the child model. Unlike `MorphOne`/
`MorphMany` it has no fixed related class — the parent type varies per row. The bound
`MorphToAccessor` is awaitable: `await comment.commentable` reads the stored `{name}_type` token,
resolves it to a class via `resolve_morph_class` (morph map, then registry fallback), and loads the
parent by `{name}_id`. Null discriminators return `None` instead of querying.

### ADR-008 § 5-02: `associate` / `dissociate`

Status: Accepted

`associate(parent)` sets `{name}_type` (via `get_morph_alias`) and `{name}_id` (`parent.get_key()`)
together, and primes the eager cache so an immediate `await child.<rel>` returns the associated
instance without a round-trip. `dissociate()` nulls both columns and clears the cache. Both are
synchronous attribute mutations (the caller saves the child) and return the child for chaining —
matching Eloquent.

### ADR-008 § 5-03: Batched eager loading grouped by type

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

### ADR-008 § 5-04: Why store the morph name (not the descriptor) on `_RelationTarget`

Status: Accepted

`_RelationTarget` carries `morph_name: str` rather than the `MorphTo[T]` descriptor. The loader only
needs the base name, and a plain `str` keeps the resolved-relation dataclass free of an unbound
generic that the strict type checkers flag as partially unknown.

---

## § 6 — MorphOne/MorphMany query + eager integration

**Originally**: ADR-068

Status: Accepted (delivered WI-arvel-028)

Epic 007 Story 3. Makes `MorphOne`/`MorphMany` first-class query relations so they participate in
`with_()`, `where_has`/`has`/`doesnt_have`, `with_count`, and `Model.load()` — not just lazy
accessor reads.

### ADR-008 § 6-01: `morph_child` relation kind

Status: Accepted

`_resolve_relation` now recognises `MorphOne`/`MorphMany` descriptors and returns a `morph_child`
target carrying a `MorphChildLink` (related model, morph base name, owner alias, and a `single` flag
for one-vs-many cardinality). The link is built from `descriptor.link_spec(get_morph_alias(model))`
so the owner token honours the morph map (ADR-008 § 4).

### ADR-008 § 6-02: Existence + count subqueries

Status: Accepted

`where_has`/`has`/`doesnt_have` and `with_count` build their subqueries against the child table with
the morph predicate pair:

```sql
... WHERE child.{name}_id = parent.pk AND child.{name}_type = '<owner-alias>'
```

Both honour the child model's global scopes (soft deletes), matching the pivot relations. The count
branch was extracted to `_morph_child_count_subquery` to keep `_count_subquery` under the complexity
gate.

### ADR-008 § 6-03: Batched eager loading

Status: Accepted

`with_("comments")` registers the relation on the async eager path (`_is_async_relation` now returns
True for `morph_child`). `batch_load_morph_children` runs a single
`WHERE {name}_type = alias AND {name}_id IN (parent_pks)` (+ any constraint-closure WHERE), groups
rows back to each parent by `{name}_id`, and stores them in the per-instance eager cache. The
`MorphOne`/`MorphMany` accessors now read that cache first (returning the single first row for
`MorphOne`, the list for `MorphMany`), so iterating after eager load is N+1-free. Nested paths
(`comments.author`) recurse through the normal async loader.

### ADR-008 § 6-04: `Model.load()` routes async relations

Status: Accepted

`Model.load(*relations)` splits its arguments: SQLAlchemy relationships still go through a
`selectinload` re-query, while async descriptor relations (BelongsToMany / MorphToMany / MorphOne /
MorphMany) batch-load into the eager cache via the new public `load_async_relation_path`. Those two
query helpers (`is_async_relation`, `load_async_relation_path`) were promoted to public wrappers so
`model.py` doesn't reach into query.py privates.

---

## § 7 — morphedByMany — inverse polymorphic many-to-many

**Originally**: ADR-069

Status: Accepted (delivered WI-arvel-029)

Epic 007 Story 4. Adds the inverse side of `MorphToMany`: the relation declared on the model the
pivot's `{name}_type`/`{name}_id` point at — e.g. `tag.posts` / `tag.videos` over one `taggables`
pivot. Mirrors Laravel's `morphedByMany`.

### ADR-008 § 7-01: `MorphedByMany` descriptor + accessor

Status: Accepted

`MorphToMany` (forward) filters the pivot by the *owner's* type and joins the related table by its
own FK column. `MorphedByMany` (inverse) flips that:

- the morph discriminator pins the **related** model's alias (`{name}_type == get_morph_alias(related)`)
- the owner's PK lives in a plain pivot FK column (`related_key`, e.g. `tag_id`)
- the related rows join back through `{name}_id`, string-cast since that column is VARCHAR:
  `pivot.{name}_id == CAST(related.pk AS VARCHAR)`

The accessor exposes `all()` / async iteration, `attach`/`detach`/`toggle`/`sync`, mirroring the
forward accessor's write semantics (idempotent attach, string-cast id on write).

### ADR-008 § 7-02: Lazy related model

Status: Accepted

Inverse relations almost always point at a model defined later in the same module (`Tag` declares
`posts` before `Post` exists). So `MorphedByMany` accepts either a class or a `lambda: Model` thunk
and resolves it lazily on first access (cached). The forward `MorphToMany` keeps its eager
`type[T]` argument — the related model is defined first there, so no thunk is needed.

### ADR-008 § 7-03: Query + eager integration (`mbm` kind)

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

---

## § 8 — has-one-of-many (latest/oldest/of_many)

**Originally**: ADR-070

Status: Accepted (delivered WI-arvel-030)

Epic 007 Story 5. Adds Laravel's `latestOfMany` / `oldestOfMany` / `ofMany` — pick exactly one
related row per owner, the winner of MAX (latest) or MIN (oldest) of a column. Two surfaces, because
the parity examples use both.

### ADR-008 § 8-01: Method style off `has_many` / `has_one`

Status: Accepted

`HasMany` and `HasOne` now share an `_OfMany` base with three coroutines:

```python
latest = await post.has_many(Comment).latest_of_many("created_at")
oldest = await post.has_many(Comment).oldest_of_many("created_at")
row    = await post.has_many(Comment).of_many("score", aggregate="max")
```

They order by the column (desc for max, asc for min) with the **PK as a deterministic tiebreaker**,
then take the first row. This is the per-instance, lazy form — no new relation type, just sugar over
the existing FK-scoped query builder.

### ADR-008 § 8-02: Descriptor style for eager loading (`HasOneOfMany`)

Status: Accepted

`has_many`/`has_one` are method-style and don't participate in `with_()`. To eager-load one-of-many
over a list, `HasOneOfMany` is a descriptor (like `MorphOne`):

```python
class Post(Model):
    latest_comment: ClassVar[HasOneOfMany[Comment]] = HasOneOfMany(
        Comment, column="created_at", aggregate="max"
    )
```

`foreign_key` defaults to `{snake(owner)}_{local_key}`. The lazy accessor (`await post.latest_comment`)
runs the same ordered `LIMIT 1` as the method form.

### ADR-008 § 8-03: Batched eager loading via a grouped subquery

Status: Accepted

`_resolve_relation` recognises `HasOneOfMany` and returns a `one_of_many` target with a
`HasOneOfManyLink`. `with_("latest_comment")` routes through the async eager engine and
`batch_load_one_of_many` runs **one** grouped subquery instead of every related row:

```sql
SELECT related.* FROM related
JOIN (SELECT fk, MAX(col) AS agg FROM related WHERE fk IN (:pks) GROUP BY fk) t
  ON related.fk = t.fk AND related.col = t.agg
```

Ties (two rows sharing the aggregate value) are resolved in Python by keeping the larger PK, so each
owner gets exactly one winner. Results land in the per-instance eager cache, so the accessor read is
N+1-free (verified by a SELECT counter: posts + one subquery = 2). Nested paths
(`latest_comment.author`) recurse through the normal loader.

### ADR-008 § 8-04: Query-builder complexity refactor

Status: Accepted

The extra relation kind pushed `_resolve_relation` and `_load_async_relation_path` past the
complexity/return-count gates, so both were split into dispatchers over focused helpers
(`_resolve_descriptor_relation` / `_resolve_morph_descriptor`, and `_load_morph_to_path` /
`_load_morph_child_path` / `_load_one_of_many_path`). Behaviour is unchanged.

---

## § 9 — chaperone (inverse parent hydration)

**Originally**: ADR-071

Status: Accepted (delivered WI-arvel-031)

Epic 007 Story 6. Adds Laravel's `chaperone` — when eager-loading a has-one/has-many, set the inverse
parent on each child so iterating `comment.post` in a loop never fires a query.

### Context

In Laravel this is a real N+1 fix: Eloquent has no identity map, so `comment.post` reloads the parent
per child. Arvel sits on SQLAlchemy, which *does* have an identity map, so within the loading session
the inverse usually resolves for free (back_populates back-fills the relation, and a many-to-one by PK
reads from the identity map without SQL). So `chaperone` here isn't about avoiding a join — it's about
a **guarantee**: each child's inverse points at the *exact* already-loaded parent instance, set as a
committed value, independent of identity-map state or whether the relationship declares
`back_populates`.

### ADR-008 § 9-01: `chaperone()` is a marker inside a `with_()` closure

Status: Accepted

```python
posts = await Post.query().with_({"comments": lambda q: q.chaperone()}).all()
for p in posts:
    for c in p.comments:
        c.post is p   # True, no query
```

`QueryBuilder.chaperone(relation=None)` sets a flag on the closure's probe builder. `with_()` runs the
closure once on a throwaway builder, reads the flag back, and records a `_Chaperone(head, inverse,
uselist)`. It composes with a filter — `lambda q: q.where(...).chaperone()` filters the children *and*
hydrates their inverse.

### ADR-008 § 9-02: Inverse resolution — back_populates, then many-to-one inference

Status: Accepted

The inverse attribute name is resolved in order:

1. Explicit: `chaperone("post")`.
2. `head_rel.back_populates` when the relationship is bidirectional.
3. Inference: scan the child mapper for a `MANYTOONE` relationship whose target is the parent model.

If none of these find an inverse, `with_()` raises `UnknownRelationError` at build time — chaperone
can't hydrate a relation the child doesn't expose.

### ADR-008 § 9-03: Hydration via `set_committed_value`

Status: Accepted

After the parent query materialises (collections already loaded by `selectinload`), `_eager_load_async`
runs `_apply_chaperones` *before* the async eager specs. For each parent it walks the loaded children
(`uselist` decides collection vs scalar) and calls
`sqlalchemy.orm.attributes.set_committed_value(child, inverse, parent)`. That's the same primitive
SQLAlchemy uses to populate a loaded relationship: no backref event (so the parent's collection isn't
mutated), no lazy query later, and identity is preserved — `child.post is parent`.

Scope: SA has-one/has-many relations (the kinds that route through `selectinload`). Pivot and morph-to
relations don't have a single inverse parent and are out of scope.

---

## § 10 — polymorphic existence queries (where_has_morph / has_morph)

**Originally**: ADR-072

Status: Accepted (delivered WI-arvel-032)

Epic 007 Story 7. Adds Laravel's `whereHasMorph` / `hasMorph` / `whereMorphRelation` — filter a
`MorphTo` against several concrete target types at once.

### Context

`where_has` already builds an `EXISTS` subquery for a single relation. A `MorphTo` (e.g.
`Comment.commentable → Post | Video`) has no single related table — the target depends on the row's
`{name}_type` token. So existence has to fan out: one branch per candidate type, each pinned to that
type's morph alias, OR'd together.

### ADR-008 § 10-01: `where_has_morph(relation, types, constraint=None)`

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

### ADR-008 § 10-02: `has_morph(relation, types, operator, count, constraint=None)`

Status: Accepted

Count-based variant. Per type it builds a correlated `COUNT` scalar subquery (mirroring
`_morph_child_count_subquery`), applies the operator/count, pins the type alias, and OR's the branches.
A `MorphTo` resolves to at most one parent, so the practical use is `>= 1`, but the general operator
form is there for parity.

### ADR-008 § 10-03: `where_morph_relation(relation, types, column, value)`

Status: Accepted

Thin sugar over `where_has_morph` — the polymorphic sibling of `where_relation`:

```python
Comment.query().where_morph_relation("commentable", [Post], "title", "keep")
```

### ADR-008 § 10-04: Scope and guards

Status: Accepted

All three resolve the relation via `_morph_to_name` and raise `UnknownRelationError` unless it's a
`MorphTo`. The closure type is a module alias `_MorphConstraint = Callable[[QueryBuilder, type], QueryBuilder]`.
These methods live on the *child* model's query (the side that owns the `{name}_type` / `{name}_id`
columns) — the owner side already has `where_has` over `MorphOne`/`MorphMany`.

---

## § 11 — relation-querying completeness

**Originally**: ADR-073

Status: Accepted (delivered WI-arvel-033)

Epic 007 Story 8. Rounds out `where_has` and friends to match Eloquent's relation-query surface:
nested paths, operator/count, `or_*` variants, constrained `doesnt_have`, `with_where_has`, and
`where_belongs_to`.

### Context

Arvel had `where_has(relation, constraint)` for a single hop with `>= 1` existence. Eloquent does a lot
more from the same family — count thresholds, OR-joined branches, walking relation chains, and the
inverse `whereBelongsTo`. These all reduce to the same primitive (a correlated `EXISTS`/`COUNT` over a
relation), so they share one recursive predicate builder rather than each method open-coding subqueries.

### ADR-008 § 11-01: `_has_predicate` — one recursive builder

Status: Accepted

`_has_predicate(model, path, constraint, operator, count)` returns a `ColumnElement[bool]`:

- Splits `path` on the first dot. The **leaf** hop carries the constraint and operator/count.
- For `>= 1` the leaf is a plain `EXISTS(subquery)`; any other operator/count uses a correlated
  `COUNT` scalar subquery compared via `_count_op`.
- **Intermediate** hops wrap a child `EXISTS` whose subquery ANDs the nested predicate, so
  `where_has("posts.comments", ...)` walks both hops with the constraint applied only at the leaf.

Every subquery runs through `apply_global_scopes`, so soft-deleted intermediates and leaves don't count.

### ADR-008 § 11-02: operator/count on `where_has`

Status: Accepted

```python
Post.query().where_has("comments", None, ">=", 3)
Post.query().where_has("comments", lambda q: q.where(Comment.spam == False), ">=", 2)
```

`_count_op` maps the operator string to the SQLAlchemy comparison. `_constrained_count_subquery`
builds the correlated `COUNT` honouring the constraint and global scopes.

### ADR-008 § 11-03: `or_*` variants

Status: Accepted

`or_where_has`, `or_doesnt_have`, and `or_where_relation` OR their predicate onto the accumulated WHERE
instead of ANDing. They reuse the same predicate builders as their AND siblings — the only difference is
the combinator. This makes `where(...).or_where_has(...)` read like Eloquent.

### ADR-008 § 11-04: constrained `doesnt_have`

Status: Accepted

`doesnt_have(relation, constraint=None)` now negates `_has_predicate`, so
`doesnt_have("comments", lambda q: q.where(Comment.spam == False))` means "no *non-spam* comment" —
matching Eloquent's `whereDoesntHave` semantics.

### ADR-008 § 11-05: `with_where_has`

Status: Accepted

```python
Post.query().with_where_has("comments", lambda q: q.where(Comment.spam == False))
```

Filters by the relation *and* eager-loads that same relation with the same constraint, so the parent is
both selected and its collection pre-filtered — Eloquent's `withWhereHas`. Implemented as
`where_has(name, constraint)` followed by `with_({name: constraint})`, reusing the existing engines.

### ADR-008 § 11-06: `where_belongs_to`

Status: Accepted

```python
Post.query().where_belongs_to(author)            # infers the FK relation
Post.query().where_belongs_to(author, "author")  # explicit relation name
```

`_belongs_to_relation_for` scans the model's mapper for the `MANYTOONE` relationship whose target class
matches the parent instance, then constrains the local FK column to the parent's key. An explicit
relation name skips inference. Raises `UnknownRelationError` when no belongs-to relation matches.

---

## § 12 — relationship aggregate completeness

**Originally**: ADR-074

Status: Accepted (delivered WI-arvel-034)

Epic 007 Story 9. Rounds out relation aggregates to match Eloquent's `withCount`/`withSum`/`withAvg`/
`withMin`/`withMax`/`withExists` plus the instance-level `loadCount`/`loadSum`/`loadAggregate`/
`loadExists`.

### Context

Arvel had `with_count` (pivot-aware) and bespoke `with_sum`/`with_max` that only handled plain SQLA
relationships — no avg/min, no exists, no pivot sum, no aliasing, no constraint closures, and no
after-the-fact instance loaders. Each method also re-derived its own correlated subquery. Since every
aggregate reduces to "scope the relation's rows, then apply an aggregate function", they now share one
builder.

### ADR-008 § 12-01: `_aggregate_column` — one builder for every aggregate

Status: Accepted

`_aggregate_column(model, target, agg, col, constraint)` resolves the relation via
`_relation_exists_select` (so it's **pivot-aware** — `BelongsToMany`/`MorphToMany`/`MorphedByMany` join
through the pivot automatically), applies the optional constraint, runs `apply_global_scopes` (so
soft-deleted related rows never count), then:

- `count` → reuses the proven `_count_subquery` (no constraint) or `_constrained_count_subquery`.
- `exists` → `select.exists()` (boolean).
- `sum`/`avg`/`min`/`max` → `with_only_columns(func.<agg>(related.col)).scalar_subquery()`.

### ADR-008 § 12-02: `with_aggregate` and the named wrappers

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

### ADR-008 § 12-03: aliasing and constraint closures

Status: Accepted

The relation string accepts an `" as <alias>"` suffix (`with_count("comments as comment_total")`), and
an explicit `alias=` kwarg wins over that. A `constraint=` closure filters the aggregated rows:

```python
Post.query().with_count("comments", constraint=lambda q: q.where(Comment.spam == False))
Post.query().with_sum("comments", "rating", alias="ham_score",
                      constraint=lambda q: q.where(Comment.spam == False))
```

Default labels match Eloquent: `{rel}_count`, `{rel}_exists`, `{rel}_{agg}_{col}`.

### ADR-008 § 12-04: instance loaders

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

---

## § 13 — pivot ergonomics for BelongsToMany

**Originally**: ADR-075

Status: Accepted (delivered WI-arvel-035)

Epic 007 Story 10. Adds Eloquent's many-to-many pivot conveniences to `BelongsToMany`:
`with_pivot`, `with_timestamps`, the `as` accessor name, `order_by_pivot`,
`where_pivot_in`/`_not_in`/`_between`/`_null`, and `create`/`save` on the relation.

### Context

`BelongsToMany` already had `attach`/`detach`/`sync`/`toggle`/`pivot`/`where_pivot`. What was missing
is the ergonomic layer Eloquent gives you when a pivot row carries data: surfacing extra pivot columns
on the related model, auto-maintaining pivot timestamps, filtering/ordering by pivot columns, and
persisting-then-attaching in one call.

### ADR-008 § 13-01: `PivotConfig` + fluent configuration

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

### ADR-008 § 13-02: `with_pivot` hydration

Status: Accepted

When pivot columns are configured, the accessor's read path (`all`, `_iter_related`, and every
`where_pivot_*`/`order_by_pivot`) selects those columns alongside the related model and attaches a
`SimpleNamespace` of them onto each row under the accessor name (default `pivot`, overridable via
`as_`). So `tag.membership.role` reads the pivot column. The eager-cache fast path is preserved — `all`
returns the cached collection without re-querying when the relation was eager-loaded.

### ADR-008 § 13-03: `with_timestamps`

Status: Accepted

`attach` fills `created_at` + `updated_at` and `update_pivot` bumps `updated_at` (both via
`datetime.now(UTC)`, only when not already supplied). `sync`/`sync_without_detaching` inherit this
through `attach`/`update_pivot`. Column names are configurable through `with_timestamps(created_at,
updated_at)`.

### ADR-008 § 13-04: pivot filters and ordering

Status: Accepted

`order_by_pivot(column, direction)`, `where_pivot_in`, `where_pivot_not_in`, `where_pivot_between`, and
`where_pivot_null(column, negate=...)` each build the join query with the owner predicate plus their
pivot predicate and return the related rows (pivot-hydrated). These are terminal `async` methods
returning `list[T]` rather than a chainable relation-query builder — the simplest surface that satisfies
each filter independently.

### ADR-008 § 13-05: `create` / `save` on the relation

Status: Accepted

```python
tag = await post.tags.create(pivot={"role": "owner"}, name="ops")  # create related + attach
await post.tags.save(existing_tag, pivot={"priority": 7})          # persist if needed + attach
```

`create` builds the related model then attaches it with optional pivot data; `save` persists an
unsaved instance (PK is null) before attaching.

### ADR-008 § 13-06: deferred — custom `Pivot` model via `using`

Status: Deferred

Eloquent's `using(PivotModel)` (a typed pivot model with its own casts/accessors) is intentionally left
out of this increment. The `SimpleNamespace` pivot accessor covers the read use case the acceptance
criteria require; a full typed pivot model is a larger abstraction and will be tracked separately.

---

## § 14 — relation defaults, eager control, and cascade save

**Originally**: ADR-076

Status: Accepted (delivered WI-arvel-036)

Epic 007 Story 11. Adds the last batch of relation ergonomics from Eloquent:
`with_default` on `BelongsTo`, `$touches`-style parent timestamp propagation,
`without()`/`with_only()` eager control, and `push()`.

### Context

`belongs_to(...)` returns a builder; when the FK is null it had no WHERE filter at all, so
`.first()` could match an arbitrary row. Eager loads were applied directly to `_stmt` inside
`with_()`, which made them impossible to drop or replace later. And there was no cascade-save or
parent-touch.

### ADR-008 § 14-01: `BelongsTo.with_default`

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

### ADR-008 § 14-02: deferred eager loads + `without` / `with_only`

Status: Accepted

`with_()` no longer mutates `_stmt`. It records each sync (selectinload) request onto
`_eager_loads` (and async/pivot requests onto `_async_eager` as before). The loader options are
materialised in `apply_global_scopes`, so they can be edited between `with_()` and execution:

- `without("posts")` drops a pending eager load by path.
- `with_only("posts")` clears all pending loads, then registers exactly the given ones.

The relation head is still validated eagerly (`_validate_eager_head`) so an unknown relation
raises `UnknownRelationError` at call time, matching the prior fail-fast behaviour.

### ADR-008 § 14-03: `$touches` and `push`

Status: Accepted

`__touches__` is a tuple of parent relation-accessor method names. After a successful `save()`,
`_touch_parents` resolves each accessor, fetches the parent, and calls `parent.touch()` — bumping
its `UPDATED_AT`. Empty by default, so it's zero-cost for models that don't opt in.

`push()` saves the model, then walks every loaded relationship in the identity map (skipping
unloaded ones) and calls `push()` on each related instance, cascading pending edits downward.

### ADR-008 § 14-04: deferred — eager column selection

Status: Deferred

Eloquent's `with("posts:id,title")` column pruning is left out. Selectin loaders hydrate full rows
into the identity map; partial column loads interact poorly with later attribute access and
expiry. Tracked separately rather than shipped half-working.

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-063 | 2026-05-18 | HasMany uses method pattern, not class-attribute descriptor | § 1 |
| ADR-064 | 2026-05-17 | BelongsToMany Pivot Attach: UPSERT on PK Conflict | § 2 |
| ADR-065 | 2026-05-18 | Soft-Delete Filter as GlobalScope | § 3 |
| ADR-066 | — | Morph map foundation | § 4 |
| ADR-067 | — | MorphTo inverse relation | § 5 |
| ADR-068 | — | MorphOne/MorphMany query + eager integration | § 6 |
| ADR-069 | — | morphedByMany — inverse polymorphic many-to-many | § 7 |
| ADR-070 | — | has-one-of-many (latest/oldest/of_many) | § 8 |
| ADR-071 | — | chaperone (inverse parent hydration) | § 9 |
| ADR-072 | — | polymorphic existence queries (where_has_morph / has_morph) | § 10 |
| ADR-073 | — | relation-querying completeness | § 11 |
| ADR-074 | — | relationship aggregate completeness | § 12 |
| ADR-075 | — | pivot ergonomics for BelongsToMany | § 13 |
| ADR-076 | — | relation defaults, eager control, and cascade save | § 14 |
