# ADR-043 — Recursive CTE anchor derived from existing WHERE scope

**Status**: Accepted
**Date**: 2026-05-18

## Context

A recursive CTE requires an "anchor" (the base case) and a "recursive step" (the join back to the
same table). The anchor must be specified. Two options: (a) require an explicit `root` parameter,
or (b) derive the anchor from the existing `.where()` scope on the builder.

## Decision

Derive the anchor from the existing `.where()` scope:

```python
# Anchor: WHERE parent_id IS NULL (already on the builder from .where())
Category.where(Category.parent_id == None).recursive("parent_id").all()

# Anchor: WHERE parent_id = :owner_id (set by has_many)
post.comments().recursive("parent_id").as_tree()
```

## Rationale

- When called after `has_many(Comment, foreign_key="parent_id")`, the FK WHERE is already on the builder. Adding `root=...` would duplicate it.
- When users write `Category.where(parent_id=None).recursive(...)`, the anchor is already expressed — no duplication.
- Fewer parameters = less cognitive load.

## Alternatives Rejected

- **Explicit `root` parameter**: `recursive(parent_key="parent_id", root=Category.parent_id.is_(None))` — redundant when used with `has_many`; users forget to add it when not using `has_many`.
