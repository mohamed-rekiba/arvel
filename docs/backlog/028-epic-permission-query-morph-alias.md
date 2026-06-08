# Epic: Role/permission query helpers ignore morph-map aliases

## Summary
`MorphToMany` stores the polymorphic `model_type` discriminator as the model's
morph alias (`get_morph_alias`), but the `query_with/without_role` and
`query_with/without_permission` class helpers filtered on the short class name.
Under any registered `morph_map` or `__morph_class__` — the recommended setup —
the tokens never match, so "with" queries returned nothing and "without" queries
returned everyone (including actual holders). Instance checks (`has_role`,
`has_permission_to`) were unaffected.

**Module:** arvel-permission · **Spec:** `docs/pipeline/specs/WI-arvel-028-permission-query-morph-alias.md`

## Stories

### Story 1: Querying models by role/permission honors morph aliases
**As a** developer building admin tooling on top of arvel-permission, **I want**
`query_with_role` / `query_without_role` / `query_with_permission` /
`query_without_permission` to return correct results when I register a morph map,
**so that** "who has/lacks this role" lists and bulk actions operate on the right
set of users.

**Acceptance Criteria**:
- [ ] Given a registered morph map alias for the host model, when calling `query_with_role`/`query_with_permission`, then only holders are returned.
- [ ] Given the same setup, when calling `query_without_role`/`query_without_permission`, then only non-holders are returned (holders are excluded).
- [ ] Given no morph map, the default short-class-name behavior is unchanged.

**Security Requirements**:
- [ ] `query_without_*` must not include privileged holders in the "lacking" set — that set commonly feeds bulk admin operations (A01-adjacent).

**Documentation Requirements**:
- [ ] `docs/site/docs/packages/permission.md` documents the query helpers and that they honor `morph_map`/`__morph_class__`.

**Requirement Refs**: C1
**Priority**: Must · **Complexity**: Small · **Status**: Done
