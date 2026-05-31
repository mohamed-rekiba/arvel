# ADR-150: chaperone (inverse parent hydration)

Status: Accepted (delivered WI-arvel-031)

Epic 007 Story 6. Adds Laravel's `chaperone` — when eager-loading a has-one/has-many, set the inverse
parent on each child so iterating `comment.post` in a loop never fires a query.

## Context

In Laravel this is a real N+1 fix: Eloquent has no identity map, so `comment.post` reloads the parent
per child. Arvel sits on SQLAlchemy, which *does* have an identity map, so within the loading session
the inverse usually resolves for free (back_populates back-fills the relation, and a many-to-one by PK
reads from the identity map without SQL). So `chaperone` here isn't about avoiding a join — it's about
a **guarantee**: each child's inverse points at the *exact* already-loaded parent instance, set as a
committed value, independent of identity-map state or whether the relationship declares
`back_populates`.

## ADR-150-01: `chaperone()` is a marker inside a `with_()` closure

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

## ADR-150-02: Inverse resolution — back_populates, then many-to-one inference

Status: Accepted

The inverse attribute name is resolved in order:

1. Explicit: `chaperone("post")`.
2. `head_rel.back_populates` when the relationship is bidirectional.
3. Inference: scan the child mapper for a `MANYTOONE` relationship whose target is the parent model.

If none of these find an inverse, `with_()` raises `UnknownRelationError` at build time — chaperone
can't hydrate a relation the child doesn't expose.

## ADR-150-03: Hydration via `set_committed_value`

Status: Accepted

After the parent query materialises (collections already loaded by `selectinload`), `_eager_load_async`
runs `_apply_chaperones` *before* the async eager specs. For each parent it walks the loaded children
(`uselist` decides collection vs scalar) and calls
`sqlalchemy.orm.attributes.set_committed_value(child, inverse, parent)`. That's the same primitive
SQLAlchemy uses to populate a loaded relationship: no backref event (so the parent's collection isn't
mutated), no lazy query later, and identity is preserved — `child.post is parent`.

Scope: SA has-one/has-many relations (the kinds that route through `selectinload`). Pivot and morph-to
relations don't have a single inverse parent and are out of scope.
