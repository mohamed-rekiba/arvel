# Epic: Raw model returns hide `__hidden__` even when nested

## Summary
The HTTP response normalizer must drop `__hidden__` columns from any model in a raw
return value, including models nested in a dict, list, or tuple. WI-032 closed the
top-level case; `return {"user": user}` still leaked password hashes / tokens.

**Module:** routing · **Spec:** `docs/pipeline/specs/WI-arvel-035-nested-model-hidden-leak.md`

## Stories

### Story 1: Hidden columns stay hidden at any nesting depth
**As a** developer returning models inside a dict/list from a route, **I want**
`__hidden__` honoured everywhere in the payload, **so that** a wrapped response
(`return {"user": user, "orders": [...]}`) can't leak a password hash — matching
Laravel's `return ['user' => $user]`.

**Acceptance Criteria**:
- [ ] Given a model in a dict value, when the route returns it without a `response_model`, then hidden columns are dropped.
- [ ] Given a list of models inside a dict, when returned, then every item drops hidden columns.
- [ ] Given a model in a nested dict, when returned, then the deep model drops hidden columns.
- [ ] Given non-model values (Pydantic models, primitives, `Response`), then they pass through untouched.

**Security Requirements**:
- [ ] No `__hidden__` column reaches the wire from a raw return at any nesting level (A09).

**Documentation Requirements**:
- [ ] `orm/models.md` notes that nested models in a raw return also honour `__hidden__`.

**Requirement Refs**: SPEC-1
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- Follow-up to WI-arvel-032 (top-level raw model return).

## Notes
- `to_dict()` reads columns only, so coerced output is plain — no recursion blow-up,
  no async relation loads triggered by the normalizer.
