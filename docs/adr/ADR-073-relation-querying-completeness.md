# ADR-073: relation-querying completeness

Status: Accepted (delivered WI-arvel-033)

Epic 007 Story 8. Rounds out `where_has` and friends to match Eloquent's relation-query surface:
nested paths, operator/count, `or_*` variants, constrained `doesnt_have`, `with_where_has`, and
`where_belongs_to`.

## Context

Arvel had `where_has(relation, constraint)` for a single hop with `>= 1` existence. Eloquent does a lot
more from the same family — count thresholds, OR-joined branches, walking relation chains, and the
inverse `whereBelongsTo`. These all reduce to the same primitive (a correlated `EXISTS`/`COUNT` over a
relation), so they share one recursive predicate builder rather than each method open-coding subqueries.

## ADR-073-01: `_has_predicate` — one recursive builder

Status: Accepted

`_has_predicate(model, path, constraint, operator, count)` returns a `ColumnElement[bool]`:

- Splits `path` on the first dot. The **leaf** hop carries the constraint and operator/count.
- For `>= 1` the leaf is a plain `EXISTS(subquery)`; any other operator/count uses a correlated
  `COUNT` scalar subquery compared via `_count_op`.
- **Intermediate** hops wrap a child `EXISTS` whose subquery ANDs the nested predicate, so
  `where_has("posts.comments", ...)` walks both hops with the constraint applied only at the leaf.

Every subquery runs through `apply_global_scopes`, so soft-deleted intermediates and leaves don't count.

## ADR-073-02: operator/count on `where_has`

Status: Accepted

```python
Post.query().where_has("comments", None, ">=", 3)
Post.query().where_has("comments", lambda q: q.where(Comment.spam == False), ">=", 2)
```

`_count_op` maps the operator string to the SQLAlchemy comparison. `_constrained_count_subquery`
builds the correlated `COUNT` honouring the constraint and global scopes.

## ADR-073-03: `or_*` variants

Status: Accepted

`or_where_has`, `or_doesnt_have`, and `or_where_relation` OR their predicate onto the accumulated WHERE
instead of ANDing. They reuse the same predicate builders as their AND siblings — the only difference is
the combinator. This makes `where(...).or_where_has(...)` read like Eloquent.

## ADR-073-04: constrained `doesnt_have`

Status: Accepted

`doesnt_have(relation, constraint=None)` now negates `_has_predicate`, so
`doesnt_have("comments", lambda q: q.where(Comment.spam == False))` means "no *non-spam* comment" —
matching Eloquent's `whereDoesntHave` semantics.

## ADR-073-05: `with_where_has`

Status: Accepted

```python
Post.query().with_where_has("comments", lambda q: q.where(Comment.spam == False))
```

Filters by the relation *and* eager-loads that same relation with the same constraint, so the parent is
both selected and its collection pre-filtered — Eloquent's `withWhereHas`. Implemented as
`where_has(name, constraint)` followed by `with_({name: constraint})`, reusing the existing engines.

## ADR-073-06: `where_belongs_to`

Status: Accepted

```python
Post.query().where_belongs_to(author)            # infers the FK relation
Post.query().where_belongs_to(author, "author")  # explicit relation name
```

`_belongs_to_relation_for` scans the model's mapper for the `MANYTOONE` relationship whose target class
matches the parent instance, then constrains the local FK column to the parent's key. An explicit
relation name skips inference. Raises `UnknownRelationError` when no belongs-to relation matches.
