# WI-arvel-029 — Password-reset storage name drift breaks forgot/reset and auth:clear-resets

- **Module**: 29 — auth (password-reset storage: migration, model, console command)
- **Complexity**: L2
- **Risk tier**: 3 (auth feature broken at runtime; A07-adjacent — account recovery)
- **Data classification**: confidential
- **Status**: completed

## Problem

The `password_resets` storage name had drifted three ways, so the feature works in
unit tests (tables built from model metadata) but breaks against the shipped
migration and console command.

1. **Migration column vs ORM column.** `create_password_resets_table` declared the
   secret column as `token`:

   ```python
   t.string("token", length=64).nullable(value=False)
   ```

   But `PasswordReset` maps it as `token_hash`, and `PasswordService` reads/writes
   `token_hash` (`PasswordReset.create(email=..., token_hash=digest)`,
   `.where(token_hash=digest)`). An app that runs the published migration gets
   `password_resets(email, token, created_at)`; the ORM then issues
   `INSERT ... (email, token_hash, ...)` → no such column (and the NOT NULL `token`
   gets no value). **Forgot/reset fails at runtime.**

2. **Console command targets the wrong table.** `auth:clear-resets` inspected and
   deleted from `password_reset_tokens`, but the actual table (migration + model)
   is `password_resets`. The command always raised
   `"password_reset_tokens table does not exist."` even when resets existed.

Sibling auth tables are internally consistent: `personal_access_tokens.token`
matches its model; `refresh_tokens.token_hash` matches its model. Only
`password_resets` was drifted.

## Repro

```text
model/ORM columns : ['email', 'token_hash', 'created_at']   (table password_resets)
migration columns : ['email', 'token', 'created_at']        (table password_resets)
console cmd table : password_reset_tokens
```

The console test masked the bug by creating its own `password_reset_tokens` table.

## Fix

Converge on the framework's canonical name — table `password_resets`, column
`token_hash` (the name the model documents and the service uses; consistent with
`refresh_tokens.token_hash`):

- Migration: `token` → `token_hash` (+ docstring).
- `auth:clear-resets`: `password_reset_tokens` → `password_resets` (inspect, delete,
  error message, help text) and regenerate `_command_meta.py`.

## Acceptance criteria

- The published migration's columns are a superset of the ORM model's columns for
  `password_resets`, `personal_access_tokens`, and `refresh_tokens` (drift guard in
  `test_framework_migrations.py`).
- `auth:clear-resets` deletes from `password_resets`.
- ruff check + format, mypy, pyright clean; auth + console + migration suites green.

## Out of scope (reviewed, no change)

- `TokenGuard` — SHA-256 hashed lookup, `hmac.compare_digest` ability check, expiry
  enforced; PAT model stores hash only, plaintext returned once. Correct.
- `PasswordService` flow — silent forgot for unknown/throttled emails (no
  enumeration), one-shot row burn, refresh-family revoke on reset. Correct.
- Laravel names `password_reset_tokens` / `token` (a bcrypt hash) differ from
  Arvel's `password_resets` / `token_hash` (sha256 hex, exact lookup). This is a
  deliberate framework convention, not flipped here.

## Files

- `packages/arvel/src/arvel/auth/migrations/create_password_resets_table.py`
- `packages/arvel/src/arvel/console/commands/auth_clear_resets.py`
- `packages/arvel/src/arvel/console/_command_meta.py` (regenerated)
- `packages/arvel/tests/database/test_framework_migrations.py` (drift guard)
- `packages/arvel/tests/console/test_command_helpers_more.py` (correct table/column)
