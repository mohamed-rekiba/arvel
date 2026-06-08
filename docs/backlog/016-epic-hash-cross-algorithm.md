# Epic: Hash.check / needs_rehash must be algorithm-aware

## Summary
The `Hash` facade hardcoded argon2id for verification, so a bcrypt hash — from
`Hash.make_bcrypt`, or an existing Laravel `users.password` column — could never be
verified: `Hash.check` raised argon2's `InvalidHashError`, which the broad `except`
swallowed, and a **correct** password silently returned `False`. `Hash.needs_rehash`
raised on the same input. Laravel's `Hash::check` is algorithm-agnostic (PHP
`password_verify` auto-detects the algorithm). `check` and `needs_rehash` now
dispatch on the hash's own prefix, restoring parity and unblocking the standard
Laravel-migration path of importing bcrypt password hashes.

**Module:** hashing · **Spec:** `docs/pipeline/specs/WI-arvel-016-hash-cross-algorithm.md`

## Stories

### Story 1: Bcrypt-hashed users can log in
**As a** team migrating from Laravel, **I want** `Hash.check` to verify the bcrypt
hashes already in my `users` table, **so that** existing users authenticate without a
forced password reset.

**Acceptance Criteria**:
- [x] Given a bcrypt hash (`$2a$`/`$2b$`/`$2y$`) and the correct password, when checked, then `Hash.check` returns `True`.
- [x] Given a bcrypt hash and a wrong password, when checked, then `Hash.check` returns `False`.
- [x] Given an argon2id hash, when checked, then verification still works (no regression).
- [x] Given an empty hash, when checked, then `Hash.check` returns `False`.

### Story 2: Rehash never crashes and drives the upgrade
**As a** developer running the rehash-on-login pattern, **I want** `Hash.needs_rehash`
to return a bool for any supported hash, **so that** bcrypt logins transparently
upgrade to the argon2id default instead of raising.

**Acceptance Criteria**:
- [x] Given a bcrypt hash, when `needs_rehash` is called, then it returns `True` (no exception).
- [x] Given a fresh argon2id hash, when `needs_rehash` is called, then it returns `False`.

**Security Requirements**:
- [x] Verification stays timing-safe (argon2 verify / bcrypt `checkpw`); no `==` on hashes (A07).
- [x] Missing `bcrypt` extra degrades to a non-match, never a crash, on the auth path.
- [x] No correct credential is silently rejected (the original defect was a hard auth-availability bug).

**Documentation Requirements**:
- [x] `docs/site/docs/features/authentication.md` states `Hash.check`/`needs_rehash` are algorithm-aware and that imported `$2y$` Laravel hashes verify and auto-upgrade.

**Requirement Refs**: SPEC-1, SPEC-2, SPEC-3, SPEC-4, SPEC-5
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001..015.

## Notes
- Folded-in: added `tests/auth/test_wi_016_hash_cross_algorithm.py` (no bcrypt-check
  coverage existed); extracted `_load_bcrypt()` so make/check share one import path.
- Deferred follow-ups (separate work items):
  - **`HashConfig` / `hashing` config block** is ignored by the facade (documented no-op).
  - **`make(**kwargs)`** arbitrary-kwarg passthrough with a `type: ignore` (ergonomics).
  - **Default algorithm** argon2id vs Laravel's bcrypt — intentional greenfield deviation.
