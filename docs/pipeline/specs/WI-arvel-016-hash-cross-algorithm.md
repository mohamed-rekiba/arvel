# WI-arvel-016 — `Hash.check` / `needs_rehash` must be algorithm-aware

- **Module**: 16 — hashing (`Hash` facade)
- **Complexity**: L2
- **Risk tier**: 3 (authentication / credential verification)
- **Data classification**: confidential (password hashes)
- **Status**: completed

## Problem

`arvel/facades/hash.py` hardcoded argon2id for verification and rehash checks,
regardless of a hash's actual algorithm.

- **C1 (Critical)** — `Hash.check` / `Hash.checkpw` called `_DEFAULT_HASHER.verify`
  (argon2) on every hash. A bcrypt hash from `Hash.make_bcrypt` (or imported from
  an existing Laravel `users.password` column) raised argon2's `InvalidHashError`,
  which the broad `except` swallowed → a **correct** password silently returned
  `False`. Every bcrypt-stored user is locked out with no error. The session guard
  (`auth/guards/session.py`) and login (`auth/auth_service.py`) both verify via
  `Hash.check`.
- **C2 (coupled)** — `Hash.needs_rehash` called argon2's `check_needs_rehash`,
  which **raised** `InvalidHashError` on a bcrypt hash instead of returning a bool.

Laravel's `Hash::check` is algorithm-agnostic (PHP `password_verify` auto-detects
the algorithm), and `Hash::needsRehash` returns `true` on an algorithm mismatch.

## Fix

Dispatch on the hash's self-identifying prefix in `hash.py`:

- `check` returns `False` for an empty hash (Laravel parity); a bcrypt-prefixed
  hash (`$2a$`/`$2b$`/`$2y$`) verifies with `bcrypt.checkpw`; everything else uses
  the argon2 path. If the `bcrypt` extra is absent, `check` returns `False` rather
  than raising — the auth path degrades gracefully.
- `needs_rehash` returns `True` for any bcrypt hash (default algorithm is argon2id,
  so a successful login transparently upgrades it); argon2 hashes defer to argon2's
  own `check_needs_rehash`.
- Extracted `_load_bcrypt()` so `make_bcrypt` and `_check_bcrypt` share the same
  import + error message.

## Acceptance criteria

- `Hash.check(pw, Hash.make_bcrypt(pw))` is `True`; wrong password is `False`.
- `Hash.check` still verifies argon2 hashes and a `$2y$` (Laravel-style) bcrypt hash.
- `Hash.check("x", "")` is `False`.
- `Hash.needs_rehash` returns `True` for a bcrypt hash and never raises.
- argon2 fresh-hash `needs_rehash` stays `False`.
- mypy --strict, pyright, ruff check, ruff format all clean; full arvel suite green.

## Out of scope (deferred)

- `HashConfig` / `hashing` config block ignored by the facade (documented no-op).
- `make(**kwargs)` arbitrary-kwarg passthrough with a type-ignore (ergonomics).
- Default-algorithm choice (argon2id vs Laravel bcrypt) — intentional deviation.

## Files

- `packages/arvel/src/arvel/facades/hash.py`
- `packages/arvel/tests/auth/test_wi_016_hash_cross_algorithm.py` (new)
- `docs/site/docs/features/authentication.md`
