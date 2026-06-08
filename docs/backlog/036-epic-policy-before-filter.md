# Epic: Policy `before` filters run in the Gate

## Summary
The authorization Gate must honour a policy's `before(user, ability)` filter — `True`
grants every ability, `False` denies every ability, `None` falls through — before
calling the per-ability method, matching Laravel.

**Module:** auth · **Spec:** `docs/pipeline/specs/WI-arvel-036-policy-before-filter.md`

## Stories

### Story 1: Policy `before` short-circuits authorization
**As a** developer writing a policy, **I want** a `before` method that authorizes (or
denies) all abilities, **so that** I can let administrators do anything or lock out a
banned user in one place — like Laravel's policy filters.

**Acceptance Criteria**:
- [ ] Given a policy `before` returning `True`, when any ability is checked, then it's granted even if the method would deny.
- [ ] Given a policy `before` returning `False`, when any ability is checked, then it's denied even if the method would allow.
- [ ] Given a policy `before` returning `None`, when an ability is checked, then it falls through to the matching method.
- [ ] Given `Policy.check(...)`, then it honours `before` with the same semantics.

**Security Requirements**:
- [ ] A `before` global-deny can't be bypassed by a permissive ability method (A01).

**Documentation Requirements**:
- [ ] `features/authorization.md` documents policy filters and the before/method order.

**Requirement Refs**: SPEC-1
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- None.

## Notes
- Order matches Laravel: gate-level `before` → policy `before` → ability method.
- Deferred (parity-additive): `Gate.after` result override (only when result is null;
  Arvel's gate always returns bool); policy resolution by subclass/inheritance walk.
