# Epic: Raw model returns leak `__hidden__` columns through the HTTP layer

## Summary
`Model.to_dict()` honours `__hidden__` / `__visible__`, but a route handler that
returns a raw model (`return user`) bypasses it: an Arvel `Model` is a
`MappedAsDataclass`, so FastAPI's encoder serialises every column — including
hidden ones like `password_hash` or `remember_token`. Laravel's `return $user;`
hides those. The fix routes raw model returns (and lists of models) through
`to_dict()` in the Router, unless the route declares an explicit `response_model`.

**Module:** ORM serialization boundary (Router response path) · **Spec:** `docs/pipeline/specs/WI-arvel-032-raw-model-hidden-leak.md`

## Stories

### Story 1: A bare `return model` keeps hidden columns hidden
**As an** app developer returning a model straight from a handler, **I want**
`__hidden__` columns excluded from the JSON response, **so that** secrets like
password hashes and tokens don't leak the way Laravel never would.

**Acceptance Criteria**:
- [ ] A route returning a raw model omits its `__hidden__` columns.
- [ ] A route returning a list of models honours hidden on every element.
- [ ] Per-instance `make_hidden(...)` is honoured (via `to_dict`).

**Security Requirements**:
- [ ] No sensitive column (password hash, token) is serialised unless explicitly
      visible (A01 / A09).

### Story 2: Existing response shapes are untouched
**As a** maintainer, **I want** the normaliser to be invisible to everything that
isn't a raw model, **so that** Pydantic returns, resources, `Response` objects,
and `response_model` routes behave exactly as before.

**Acceptance Criteria**:
- [ ] Dict / Pydantic / `Response` returns pass through unchanged.
- [ ] Routes with an explicit `response_model` are left to FastAPI.
- [ ] Handler signature (params, dependencies) is preserved.

**Requirement Refs**: C1 (FastAPI dataclass encoding bypasses `__hidden__` on raw model returns)
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Follow-ups (not in this WI)
- Models nested inside a returned dict/list-of-dicts still encode via FastAPI and
  would leak; idiomatic responses use a resource/schema. A recursive encoder is a
  separate, heavier decision.
- Insecure-by-default mass assignment (no `__fillable__`/`__guarded__` ⇒ all
  columns assignable) diverges from Laravel's `$guarded = ['*']`; a deliberate
  design call, tracked separately.
