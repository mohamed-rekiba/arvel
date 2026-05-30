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

### Story 1: Morph map foundation
**As a** developer, **I want** `Relation.morph_map({...})`, `Model.get_morph_class()`, and an optional `require_morph_map()`, **so that** polymorphic type tokens are stable aliases I control rather than raw class names — surviving refactors and cross-package moves.

**Acceptance Criteria**:
- [ ] Given a registered morph map, when a polymorphic row is written, then the configured alias is stored in `{name}_type`.
- [ ] Given `get_morph_class()`, then it returns the alias when mapped, else the default token.
- [ ] Given `require_morph_map()` enabled, when an unmapped model is used polymorphically, then it raises.

**Documentation Requirements**:
- [ ] Document morph map registration and migration considerations (supersedes the unqualified-name approach in ADR-022).

**Priority**: Must
**Complexity**: Medium

### Story 2: `MorphTo` inverse relation
**As a** developer modeling `comment.commentable`, **I want** a `MorphTo` descriptor with batched eager loading by type and `associate`/`dissociate`, **so that** child models can resolve and set their polymorphic parent.

**Acceptance Criteria**:
- [ ] Given a `MorphTo` relation, when accessed, then it resolves the parent using `{name}_type` + `{name}_id`.
- [ ] Given a list of children eager-loaded with the morphTo, then parents are batch-loaded grouped by type (one query per distinct type).
- [ ] Given `associate(model)`/`dissociate()`, then the type and id are set/cleared together.

**Priority**: Must
**Complexity**: Large

### Story 3: MorphOne/MorphMany query + eager integration
**As a** developer, **I want** `MorphOne`/`MorphMany` registered in `_resolve_relation` so they work with `with_()`, `where_has`, `with_count`, and `Model.load()`, **so that** list endpoints can batch-load morph children instead of silently lazy-loading.

**Acceptance Criteria**:
- [ ] Given `Post.query().with_("comments")` where `comments` is `MorphMany`, then comments batch-load in one query.
- [ ] Given `where_has("comments", ...)`, then it filters via an EXISTS subquery with the morph type predicate.
- [ ] Given `with_count("comments")`, then a correct per-parent count column is added.

**Priority**: Must
**Complexity**: Large

### Story 4: `morphed_by_many` (inverse morph pivot)
**As a** developer with a Spatie-style permission/tag model, **I want** `morphed_by_many(Model, ...)`, **so that** I can query "all models that have this role/tag" from the related side.

**Acceptance Criteria**:
- [ ] Given `Role.users = morphed_by_many(User, ...)`, then it queries the pivot with the FK columns swapped and the morph type pinned to `User`.
- [ ] Eager loading and `attach`/`detach` work from the inverse side.

**Priority**: Should
**Complexity**: Medium

### Story 5: `of_many` / `latest_of_many` / `oldest_of_many`
**As a** developer, **I want** `has_one(...).latest_of_many("created_at")` (and `oldest_of_many`/`of_many`), **so that** "the latest comment per post" is a single aggregated relation rather than a manual subquery.

**Acceptance Criteria**:
- [ ] Given `latest_of_many`, when eager-loaded over a list, then each parent gets exactly one related row (the max by the given column).
- [ ] Given `of_many(column, aggregate)`, then the configured aggregate selects the row.

**Priority**: Should
**Complexity**: Large

### Story 6: Chaperone (inverse parent hydration)
**As a** developer iterating children after eager loading, **I want** an opt-in `chaperone` that sets the parent on each child during eager load, **so that** accessing `comment.post` in a loop doesn't trigger N+1.

**Acceptance Criteria**:
- [ ] Given `Post.query().with_({"comments": lambda q: q.chaperone()})`, when iterating `post.comments` and accessing `comment.post`, then no extra query runs.
- [ ] The hydrated parent is the already-loaded instance (identity preserved).

**Priority**: Should
**Complexity**: Medium

### Story 7: Polymorphic existence queries
**As a** developer, **I want** `where_has_morph`/`has_morph`/`where_morph_relation`, **so that** I can filter by polymorphic relations across multiple target types.

**Acceptance Criteria**:
- [ ] Given `where_has_morph("commentable", [Post, Video], constraint)`, then it builds a per-type EXISTS subquery union.
- [ ] Works with the morph map aliases from Story 1.

**Priority**: Could
**Complexity**: Large

### Story 8: Relation-querying completeness
**As a** developer, **I want** nested `where_has` paths, `or_*` relation variants (`or_where_has`, `or_doesnt_have`, `or_where_relation`), a `doesnt_have` constraint closure, `where_has` with operator+count, `with_where_has`, and `where_belongs_to`, **so that** relation filtering matches Laravel.

**Acceptance Criteria**:
- [ ] Given `where_has("posts.comments", ...)`, then the nested EXISTS subquery walks both hops.
- [ ] Given `or_where_has(...)`, then the existence condition is OR-joined.
- [ ] Given `with_where_has("posts", c)`, then the relation is both filtered and eager-loaded with the same constraint.
- [ ] Given `where_belongs_to(parent)`, then it filters by the parent's FK.

**Priority**: Should
**Complexity**: Medium

### Story 9: Relationship aggregate completeness
**As a** developer, **I want** `with_avg`/`with_min`/`with_exists`, pivot-aware `with_sum`/`with_max`, aggregate aliasing and constraint closures, and instance `load_count`/`load_sum`/`load_aggregate`/`load_exists`, **so that** aggregates cover all relation types and can be loaded after the fact.

**Acceptance Criteria**:
- [ ] Given `with_avg("comments", "rating")`, then an average column is added per parent.
- [ ] Given `with_sum` over a `BelongsToMany`/`MorphToMany`, then the sum joins via the pivot.
- [ ] Given `await post.load_count("comments")`, then the count is computed and cached on the instance.
- [ ] Aggregate columns can be aliased (`comments as comment_total`).

**Priority**: Should
**Complexity**: Medium

### Story 10: Pivot ergonomics
**As a** developer using many-to-many, **I want** `with_pivot` (extra columns hydrated onto related models), `with_timestamps`, `order_by_pivot`, `where_pivot_in`/`_not_in`/`_between`/`_null`, a custom `Pivot` model via `using`, an `as` accessor name, and `save`/`create` on the relation, **so that** pivot-heavy apps are concise and type-safe.

**Acceptance Criteria**:
- [ ] Given `with_pivot("expires_at")`, when loaded, then the pivot column is accessible on each related model's pivot accessor.
- [ ] Given `with_timestamps`, then `attach`/`sync` set pivot `created_at`/`updated_at`.
- [ ] Given `order_by_pivot("created_at")`, then results are ordered by the pivot column.
- [ ] Given `where_pivot_in("role", [...])` etc., then the pivot filter applies.

**Priority**: Should
**Complexity**: Large

### Story 11: Relation defaults, eager control, and cascade save
**As a** developer, **I want** `with_default` (empty `belongs_to`/`has_one`), `$touches`-style parent timestamp propagation, `without()`/`with_only()` eager control, eager column selection (`with("posts:id,title")`), and `push()` (save with loaded relations), **so that** relation ergonomics match Laravel.

**Acceptance Criteria**:
- [ ] Given `belongs_to(...).with_default(factory)`, when the FK is null, then a default instance is returned instead of `None`.
- [ ] Given a child save with `touches=["post"]`, then the parent's `updated_at` is bumped.
- [ ] Given `with_only("comments")`, then only that relation is eager-loaded (others cleared).
- [ ] Given `await model.push()`, then the model and its dirty loaded relations are saved.

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
