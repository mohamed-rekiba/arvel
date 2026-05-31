# Epic: Relationship Parity with Laravel

## Summary

Close the relationship gap between Arvent and Laravel Eloquent. Covers inverse polymorphism,
the morph map, morph-child query/eager integration, "one of many", chaperone, relation-existence
queries, relationship aggregates, and pivot ergonomics. Findings come from the parity review
against `repos/lv-app/vendor/laravel/framework/src/Illuminate/Database/Eloquent/Relations` and the
`HasRelationships` / `QueriesRelationships` concerns.

Arvel already has `has_one`/`has_many`/`belongs_to`, `BelongsToMany`/`MorphToMany` (owner side),
`*_through`, batched eager loading for pivot relations (epic-from-prior-work), `with_count`,
`where_has`/`has`/`doesnt_have`, and core pivot ops. The stories below add the missing relation
types and ergonomics.

## Stories

### Story 1: Morph map foundation — DONE (WI-arvel-026, ADR-145)
**As a** developer, **I want** `Relation.morph_map({...})`, `Model.get_morph_class()`, and an optional `require_morph_map()`, **so that** polymorphic type tokens are stable aliases I control rather than raw class names — surviving refactors and cross-package moves.

**Acceptance Criteria**:
- [x] Given a registered morph map, when a polymorphic row is written, then the configured alias is stored in `{name}_type` (wired through `get_morph_alias` in MorphOne/MorphMany/MorphToMany write paths).
- [x] Given `get_morph_class()`, then it returns the alias when mapped, else the default token (short class name).
- [x] Given `require_morph_map()` enabled, when an unmapped model is used polymorphically, then it raises `MorphMapError`.

**Documentation Requirements**:
- [x] Morph map registration + migration documented in ADR-145 (supersedes the unqualified-name default of ADR-022) and the docs site.

**Priority**: Must
**Complexity**: Medium

### Story 2: `MorphTo` inverse relation — DONE (WI-arvel-027, ADR-146)
**As a** developer modeling `comment.commentable`, **I want** a `MorphTo` descriptor with batched eager loading by type and `associate`/`dissociate`, **so that** child models can resolve and set their polymorphic parent.

**Acceptance Criteria**:
- [x] Given a `MorphTo` relation, when accessed, then it resolves the parent using `{name}_type` + `{name}_id` (token → class via `resolve_morph_class`).
- [x] Given a list of children eager-loaded with the morphTo, then parents are batch-loaded grouped by type (one query per distinct type — verified by SELECT counter: 1 + one per distinct type).
- [x] Given `associate(model)`/`dissociate()`, then the type and id are set/cleared together (associate also primes the eager cache).

**Priority**: Must
**Complexity**: Large

### Story 3: MorphOne/MorphMany query + eager integration — DONE (WI-arvel-028, ADR-147)
**As a** developer, **I want** `MorphOne`/`MorphMany` registered in `_resolve_relation` so they work with `with_()`, `where_has`, `with_count`, and `Model.load()`, **so that** list endpoints can batch-load morph children instead of silently lazy-loading.

**Acceptance Criteria**:
- [x] Given `Post.query().with_("comments")` where `comments` is `MorphMany`, then comments batch-load in one query (verified by SELECT counter: 2 total for posts + comments).
- [x] Given `where_has("comments", ...)`, then it filters via an EXISTS subquery with the morph type predicate (constraint closures supported).
- [x] Given `with_count("comments")`, then a correct per-parent count column is added.
- [x] Bonus: `doesnt_have`, `MorphOne` eager, and `Model.load("comments")` onto an existing instance all work.

**Priority**: Must
**Complexity**: Large

### Story 4: `morphed_by_many` (inverse morph pivot) — DONE (WI-arvel-029, ADR-148)
**As a** developer with a Spatie-style permission/tag model, **I want** `MorphedByMany(Model, ...)`, **so that** I can query "all models that have this role/tag" from the related side.

**Acceptance Criteria**:
- [x] Given `Tag.posts = MorphedByMany(Post, ...)`, then it queries the pivot with the owner FK as `related_key` and the morph type pinned to the related model's alias (joins `{name}_id` to the related PK, string-cast).
- [x] Eager loading (`with_`, N+1-free) and `attach`/`detach`/`toggle`/`sync` work from the inverse side.
- [x] Bonus: `where_has` and `with_count` work from the inverse side; related model accepts a `lambda:` thunk for forward references.

**Priority**: Should
**Complexity**: Medium

### Story 5: `of_many` / `latest_of_many` / `oldest_of_many` — DONE (WI-arvel-030, ADR-149)
**As a** developer, **I want** `has_one(...).latest_of_many("created_at")` (and `oldest_of_many`/`of_many`), **so that** "the latest comment per post" is a single aggregated relation rather than a manual subquery.

**Acceptance Criteria**:
- [x] Given the `HasOneOfMany` descriptor, when eager-loaded over a list via `with_()`, then each parent gets exactly one related row (max/min by the column) in a single grouped subquery (N+1-free, verified by SELECT counter).
- [x] Given `of_many(column, aggregate)` / `latest_of_many` / `oldest_of_many` off `has_many`/`has_one`, then the configured aggregate selects the row (PK tiebreaker for determinism).

**Priority**: Should
**Complexity**: Large

### Story 6: Chaperone (inverse parent hydration) — DONE (WI-arvel-031, ADR-150)
**As a** developer iterating children after eager loading, **I want** an opt-in `chaperone` that sets the parent on each child during eager load, **so that** accessing `comment.post` in a loop doesn't trigger N+1.

**Acceptance Criteria**:
- [x] Given `Post.query().with_({"comments": lambda q: q.chaperone()})`, when iterating `post.comments` and accessing `comment.post`, then no extra query runs (verified by SELECT counter).
- [x] The hydrated parent is the already-loaded instance (identity preserved — `child.post is parent`, via `set_committed_value`). Inverse resolved by explicit name → `back_populates` → many-to-one inference; composes with a filtering closure.

**Priority**: Should
**Complexity**: Medium

### Story 7: Polymorphic existence queries — DONE (WI-arvel-032, ADR-151)
**As a** developer, **I want** `where_has_morph`/`has_morph`/`where_morph_relation`, **so that** I can filter by polymorphic relations across multiple target types.

**Acceptance Criteria**:
- [x] Given `where_has_morph("commentable", [Post, Video], constraint)`, then it builds a per-type EXISTS subquery union (OR'd, each scoped + alias-pinned). Constraint closure receives `(query, type_model)`.
- [x] Works with the morph map aliases from Story 1 (`get_morph_alias` → registered `morph_map` honoured). Plus `has_morph` (count-based) and `where_morph_relation` (column sugar); non-MorphTo relation raises `UnknownRelationError`.

**Priority**: Could
**Complexity**: Large

### Story 8: Relation-querying completeness — DONE (WI-arvel-033, ADR-152)
**As a** developer, **I want** nested `where_has` paths, `or_*` relation variants (`or_where_has`, `or_doesnt_have`, `or_where_relation`), a `doesnt_have` constraint closure, `where_has` with operator+count, `with_where_has`, and `where_belongs_to`, **so that** relation filtering matches Laravel.

**Acceptance Criteria**:
- [x] Given `where_has("posts.comments", ...)`, then the nested EXISTS subquery walks both hops (recursive `_has_predicate`, constraint applied at the leaf).
- [x] Given `or_where_has(...)`, then the existence condition is OR-joined. Same for `or_doesnt_have`/`or_where_relation`. `where_has`/`doesnt_have` take an operator+count and a constraint closure.
- [x] Given `with_where_has("posts", c)`, then the relation is both filtered and eager-loaded with the same constraint.
- [x] Given `where_belongs_to(parent)`, then it filters by the parent's FK (relation inferred by MANYTOONE target match, or named explicitly).

**Priority**: Should
**Complexity**: Medium

### Story 9: Relationship aggregate completeness — DONE (WI-arvel-034, ADR-153)
**As a** developer, **I want** `with_avg`/`with_min`/`with_exists`, pivot-aware `with_sum`/`with_max`, aggregate aliasing and constraint closures, and instance `load_count`/`load_sum`/`load_aggregate`/`load_exists`, **so that** aggregates cover all relation types and can be loaded after the fact.

**Acceptance Criteria**:
- [x] Given `with_avg("comments", "rating")`, then an average column is added per parent. Plus `with_min`/`with_exists`; all route through `_aggregate_column`/`with_aggregate`.
- [x] Given `with_sum` over a `BelongsToMany`/`MorphToMany`, then the sum joins via the pivot (`_relation_exists_select` is pivot-aware).
- [x] Given `await post.load_count("comments")`, then the count is computed and cached on the instance. Plus `load_sum`/`load_exists`/`load_aggregate` (avg/min/max), each cached under its label.
- [x] Aggregate columns can be aliased (`"comments as comment_total"` or `alias=`), and a `constraint=` closure filters the aggregated rows (soft-delete scoped).

**Priority**: Should
**Complexity**: Medium

### Story 10: Pivot ergonomics — DONE (WI-arvel-035, ADR-154)
**As a** developer using many-to-many, **I want** `with_pivot` (extra columns hydrated onto related models), `with_timestamps`, `order_by_pivot`, `where_pivot_in`/`_not_in`/`_between`/`_null`, a custom `Pivot` model via `using`, an `as` accessor name, and `save`/`create` on the relation, **so that** pivot-heavy apps are concise and type-safe.

**Acceptance Criteria**:
- [x] Given `with_pivot("expires_at")`, when loaded, then the pivot column is accessible on each related model's pivot accessor (SimpleNamespace under the `as_` name, default `pivot`).
- [x] Given `with_timestamps`, then `attach`/`sync`/`update_pivot` set pivot `created_at`/`updated_at`.
- [x] Given `order_by_pivot("created_at")`, then results are ordered by the pivot column (asc/desc).
- [x] Given `where_pivot_in("role", [...])`, `where_pivot_not_in`, `where_pivot_between`, `where_pivot_null(negate=...)`, then the pivot filter applies. Plus `create`/`save` on the relation and the `as_` accessor name.

**Note**: custom `Pivot` model via `using` is deferred (ADR-154-06) — not in the AC; the `SimpleNamespace` pivot accessor covers the required read surface.

**Priority**: Should
**Complexity**: Large

### Story 11: Relation defaults, eager control, and cascade save — DONE (WI-arvel-036, ADR-155)
**As a** developer, **I want** `with_default` (empty `belongs_to`/`has_one`), `$touches`-style parent timestamp propagation, `without()`/`with_only()` eager control, eager column selection (`with("posts:id,title")`), and `push()` (save with loaded relations), **so that** relation ergonomics match Laravel.

**Acceptance Criteria**:
- [x] Given `belongs_to(...).with_default(...)`, when the FK is null or unmatched, then a default instance is returned instead of `None` (empty, dict of attributes, or a `(instance, owner)` callback).
- [x] Given a child with `__touches__ = ("author_relation",)`, when it's saved, then each named parent's `updated_at` is bumped (via `Model._touch_parents`).
- [x] Given `with_only("comments")`, then only that relation is eager-loaded (others cleared); `without("comments")` drops a pending eager load. Eager loads are deferred to `apply_global_scopes` so they can be edited before the SELECT is built.
- [x] Given `await model.push()`, then the model and every loaded relation (recursively) are saved.

**Note**: eager column selection (`with("posts:id,title")`) is deferred (ADR-155-04) — not in the AC; selectin loaders fetch full rows, and column pruning interacts poorly with identity-map hydration. Tracked separately.

**Priority**: Could
**Complexity**: Large

## Dependencies

- Story 1 (morph map) is the foundation for Stories 2, 3, 4, and 7.
- Sequencing: morph map → MorphTo → MorphOne/Many integration → hasMorph/whereHasMorph.
- Story 9's instance loaders and Story 3's eager engine reuse the batched pivot loader and the
  per-instance eager cache from the prior eager-loading work.

## Notes

- Laravel references: `Eloquent/Relations/{MorphTo,MorphOne,MorphMany,MorphToMany,BelongsToMany,Relation}.php`,
  `Concerns/HasRelationships.php`, `Concerns/QueriesRelationships.php`, `Eloquent/Concerns/CanBeOneOfMany.php`,
  `SupportsInverseRelations.php`, `SupportsDefaultModels.php`.
- The local Laravel vendor tree is the source of truth; verify exact signatures there during
  implementation (one review pass referenced 13.x conventions and should be re-checked against
  the pinned vendor version).
