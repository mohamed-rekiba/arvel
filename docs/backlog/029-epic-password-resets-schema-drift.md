# Epic: Password-reset storage name drift breaks forgot/reset and auth:clear-resets

## Summary
The `password_resets` storage name had drifted three ways. The shipped migration
declared the secret column as `token`, but the `PasswordReset` model and
`PasswordService` use `token_hash`, so an app running the published migration hits
"no such column: token_hash" on the first forgot/reset. Separately, the
`auth:clear-resets` console command targeted a `password_reset_tokens` table that
doesn't exist (the real table is `password_resets`), so it always failed. Unit
tests passed because they build tables from model metadata, not the migration, and
the console test created the wrong-named table itself.

**Module:** auth · **Spec:** `docs/pipeline/specs/WI-arvel-029-password-resets-schema-drift.md`

## Stories

### Story 1: Published migration matches the ORM model
**As a** developer who runs `arvel migrate`, **I want** the `password_resets`
migration columns to match what the `PasswordReset` model reads and writes, **so
that** forgot-password and reset-password work against a freshly migrated database.

**Acceptance Criteria**:
- [ ] The migration creates `password_resets(email, token_hash, created_at)`.
- [ ] A drift guard asserts the migration columns cover the ORM model columns for `password_resets`, `personal_access_tokens`, and `refresh_tokens`.
- [ ] Forgot/reset round-trips against a DB built from the migration.

**Security Requirements**:
- [ ] The secret column stores only the sha256 hex digest, never the plaintext.

### Story 2: auth:clear-resets targets the real table
**As an** operator pruning expired reset tokens, **I want** `auth:clear-resets` to
delete from `password_resets`, **so that** the maintenance command actually works.

**Acceptance Criteria**:
- [ ] `auth:clear-resets` inspects and deletes from `password_resets`.
- [ ] Missing-table error names `password_resets`.
- [ ] `_command_meta.py` help text matches the command's `help` (drift guard green).

**Documentation Requirements**:
- [ ] Schema documented in the migration docstring; CLI table lists the command.

**Requirement Refs**: C1 (migration column), C2 (console table name)
**Priority**: Must · **Complexity**: Small · **Status**: Done
