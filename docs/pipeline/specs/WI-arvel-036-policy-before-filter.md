# WI-arvel-036 — Gate ignores policy `before` filters (broken access control)

- **Module:** 36 (auth / authorization Gate + Policy)
- **Complexity:** L2
- **Risk tier:** 3 (authorization)
- **Data classification:** internal
- **Status:** completed

## Problem

`Gate.allows()` resolved a registered policy by calling the ability method directly
(`getattr(policy, ability)`). It never invoked the policy's `before` method. Laravel
runs a policy `before(user, ability)` filter before any ability method — a non-null
return short-circuits: `True` grants every ability, `False` denies every ability,
`None` falls through.

Skipping it is an A01 broken-access-control gap in both directions:

- A policy `before` that returns `False` to lock out a banned/suspended user was
  silently ignored — the per-ability method could still grant access.
- A policy `before` that returns `True` for administrators was ignored — admins were
  denied whenever the specific ability method returned false.

`Policy.check()` (the lower-level public helper) had the same omission.

## Fix

- `Gate.allows()` policy branch: call `policy.before(user, ability)` first (sync or
  async). If it returns non-null, run after-hooks and return that result. Otherwise
  fall through to the ability method (now resolved with `getattr(..., None)` +
  `callable` so a non-method attribute can't be invoked).
- `Policy.check()`: same `before` short-circuit before the ability lookup.

Gate-level `before` hooks still run first (unchanged), matching Laravel's order:
gate before → policy before → ability method.

## Tests

`packages/arvel/tests/auth/test_gate.py` (+6):
- policy `before` grants all for admin (overrides a denying method)
- policy `before` denies all for banned (overrides an allowing method)
- policy `before` returning `None` falls through to the method
- `Policy.check()` honours `before`

## Out of scope (noted)

- `Gate.after` callbacks can override the result in Laravel only when the gate/policy
  returned `null`; Arvel's gate always returns bool, so this never triggers — left as
  a parity-additive follow-up.
- Policy resolution matches the exact runtime type only (no subclass/inheritance walk).

## Gates

ruff check + format clean; mypy 0 issues (1065 files); pyright 0 errors/0 warnings;
gate suite 14 passed.
