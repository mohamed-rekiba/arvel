# ADR-007 — Resource OpenAPI schemas are opt-in via ClassVar, not AST introspection

**Date**: 2026-05-17
**Status**: Accepted
**Deciders**: Solution Architect (autonomous)
**Scope**: `arvel.http.resources.JsonResource`

---

## Context

`JsonResource[T]` lets developers shape a response with a `to_dict(request)` method. The framework needs to give FastAPI a `response_model` so OpenAPI documents the shape correctly. Three options:

1. **Infer the schema from `to_dict` by AST introspection** — parse the method body, derive types from the dict literal returned.
2. **Always emit `dict[str, object]`** — accurate, useless for client codegen.
3. **Opt-in `ClassVar` schema** — let the developer point at a Pydantic model that documents the shape.

## Decision

Adopt option 3. `JsonResource[T]` subclasses MAY declare a class-level `schema: ClassVar[type[BaseModel]]`. If present, FastAPI gets that schema as the response model. If absent, the response is typed as `dict[str, object]`.

```python
class UserPublic(BaseModel):
    id: int
    email: EmailStr
    links: dict[str, str]

class UserResource(JsonResource[User]):
    schema: ClassVar[type[BaseModel]] = UserPublic

    def to_dict(self, request: Request) -> dict[str, object]:
        return UserPublic(
            id=self.resource.id,
            email=self.resource.email,
            links={"self": str(request.url_for("users.show", id=self.resource.id))},
        ).model_dump()
```

`ResourceCollection[T]` works the same way; the auto-generated envelope schema is `{ "data": list[schema] }`.

## Why opt-in

- AST introspection is brittle: any `if/else`, comprehension, or method call in `to_dict` breaks it. The result would be silently wrong for OpenAPI consumers.
- `dict[str, object]` as the default keeps the contract honest: if you didn't tell me the shape, I won't lie about it.
- The `ClassVar` shape is purely declarative — no decorators, no metaclass.
- Pyright/mypy both treat `ClassVar[type[BaseModel]]` correctly with no special handling.

## Trade-off accepted

- Slightly more verbose than "magical inference" — developers write the Pydantic schema explicitly. The constitution (Article VIII.1) values predictability over magic.
- Some users will skip the schema entirely; their OpenAPI is uninformative. We document this as a known trade-off, not a bug.

## Consequences

- `JsonResource[T]` has minimal metaclass / `__init_subclass__` involvement — keeps mypy/pyright happy.
- A future WI can add a `@auto_schema` decorator that generates the Pydantic model from a TypedDict if there's demand. Not now (YAGNI).

---

## Cross-references

- PRD-002: FR-002-010, FR-002-011, FR-002-012
- SAD-002 §3 (Resources component)
