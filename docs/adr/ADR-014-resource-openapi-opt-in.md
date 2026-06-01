# ADR-014 — Resource OpenAPI schemas are opt-in via ClassVar, not AST introspection

**Date**: 2026-05-17
**Status**: Accepted
**Last reconciled**: 2026-06-01
**Deciders**: Solution Architect (autonomous)
**Scope**: `arvel.http.resources`

---

## Context

`JsonResource[T]` shapes a response via a `to_dict(request)` method. FastAPI needs a `response_model` to document the shape in OpenAPI. Options: infer the schema from `to_dict` by AST introspection (brittle); always emit `dict[str, object]` (accurate, useless for client codegen); or an opt-in `ClassVar` schema pointing at a Pydantic model.

## Decision

**Opt-in `ClassVar` schema.** A `JsonResource[T]` subclass MAY declare a class-level `schema: ClassVar[type[BaseModel]]`. If present, FastAPI gets that schema as the response model; if absent, the response is typed as `dict[str, object]`. The resource-collection variant reuses the same mechanism, wrapping the declared schema in a `{ "data": list[schema] }` envelope.

```python
class UserPublic(BaseModel):
    id: int
    email: EmailStr

class UserResource(JsonResource[User]):
    schema: ClassVar[type[BaseModel]] = UserPublic

    def to_dict(self, request: Request) -> dict[str, object]:
        return UserPublic(id=self.resource.id, email=self.resource.email).model_dump()
```

## Why opt-in

- AST introspection breaks on any `if/else`, comprehension, or method call in `to_dict`, and would be silently wrong for OpenAPI consumers.
- `dict[str, object]` as the default keeps the contract honest: no declared shape, no schema claim.
- The `ClassVar` is purely declarative — no decorators, no metaclass — and both strict checkers handle `ClassVar[type[BaseModel]]` with no special casing.

## Trade-off accepted

Slightly more verbose than magical inference: developers write the Pydantic schema explicitly. The constitution (Article VIII.1) values predictability over magic. Resources without a schema produce uninformative OpenAPI — a documented trade-off, not a bug.

## Current implementation

- Code: `packages/arvel/src/arvel/http/resources.py`.
- Docs: `docs-fresh/http/resources.md`.
