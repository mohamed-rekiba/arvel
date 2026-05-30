# ADR-041 — HasMany uses method pattern, not class-attribute descriptor

**Status**: Accepted
**Date**: 2026-05-18

## Context

Simple FK relations (`HasMany`, `HasOne`, `BelongsTo`) need to return a `QueryBuilder[T]`
so users can chain `.where()`, `.order_by()`, `.recursive()`, etc. Two patterns were considered:
(1) class-attribute descriptors like `BelongsToMany`, and (2) instance methods returning a builder.

## Decision

Use **instance methods**:

```python
class Post(Model):
    def comments(self) -> HasMany[Comment]:
        return self.has_many(Comment)
```

## Rationale

- No `__get__` / `__set_name__` overload complexity
- Arbitrary constraints can be applied at definition time (e.g., `self.has_many(Comment).where(approved=True)`)
- Return type is explicit and statically checkable: `HasMany[Comment]` (a `QueryBuilder[T]` subclass)
- Consistent with how users write scopes — just an instance method returning a builder
- `BelongsToMany` uses descriptors for historical reasons (WI-003); new relations don't need to match that

## Alternatives Rejected

- **Class-attribute descriptor**: Requires `__get__` to receive `self`; complicates applying initial WHERE scopes; harder to type-check the generic parameter.
