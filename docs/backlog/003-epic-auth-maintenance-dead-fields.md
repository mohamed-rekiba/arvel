# Epic: Auth & Maintenance dead-field cleanup

## Summary

Four fields in `arvel.auth` and `arvel.maintenance` are part of the public surface but inert: `AuthConfig` accepts `driver: "arvent"` and the runtime raises (the `_build_provider` switch only handles `"database"`); `LoginRequest.remember` + `users.remember_token` exist but no code reads them; `MaintenanceModeManager` stores a `template` path that `MaintenanceModeMiddleware` never renders; `ArraySessionStore` is implemented but absent from `SessionManager._create`. Greenfield — either wire the field or delete it.

## Audit reference

`auth audit` (parallel review pass, 2026-06-05) — `[Critical Gaps]` and `[Code Quality]` sections.

## Stories

### Story 1: `arvent` auth provider driver works, or is removed from the schema (RESOLVED — IMPLEMENTED)

> **Resolution**: `arvent` is the canonical (and only valid) driver name. `DatabaseUserProvider` → `ArventUserProvider`; module renamed `auth.providers.database` → `auth.providers.arvent`. `ProviderConfig.driver` now has a `field_validator` that rejects unknown drivers at config load time with a clear "Valid drivers: arvent." error. Site doc updated.

**As a** Laravel migrant, **I want** `config/auth.py` with `provider.driver: "arvent"` to either load Arvent models successfully or fail at config time, **so that** I don't hit a runtime trap on first authentication.

**Acceptance Criteria**:
- [ ] Given `AuthConfig` with `provider.driver = "arvent"`, when `_build_provider` runs, then it either returns a working `ArventUserProvider` (preferred) or `AuthConfig` validation rejects the value at load time with a clear error pointing at the valid drivers.
- [ ] If implemented: given an `ArventUserProvider` configured with `model: "app.models.User"`, when `Auth::attempt({email, password})` runs, then it resolves the model class, hashes/checks via `Hash::check`, and returns a populated `User` instance on success.
- [ ] If removed: given the deleted driver name, when a user includes it in config, then `AuthConfig` `field_validator` rejects with: `"driver must be one of: database"` and the docs are updated.
- [ ] Tests cover both the happy path and the rejection path.

**Security Requirements**:
- [ ] No timing leak — `Hash::check` must run regardless of whether the user lookup returned a row (constant-time semantics).

**Documentation Requirements**:
- [ ] `docs/site/docs/security/authentication.md` lists the valid providers and matches code.

**Requirement Refs**: AUDIT-AUTH-CRITICAL-1
**Priority**: Must
**Complexity**: Medium (if implemented) / Small (if removed)
**Status**: Ready

---

### Story 2: `remember` is wired into the login flow, or removed (RESOLVED — REMOVED)

> **Resolution**: per the greenfield rule, the inert `LoginRequest.remember` field, `users.remember_token` column (in the model and migration), and `__hidden__` reference were deleted. The auth feature doc now explicitly notes remember-me is not implemented. Implementing it properly (token rotation, hashed storage, scoped cookies, SessionGuard pickup) remains a future feature.

**As a** session-auth user, **I want** ticking the "remember me" box to give me a long-lived cookie, **so that** I don't have to log in every session.

**Acceptance Criteria**:
- [ ] Given `LoginRequest.remember = True`, when login succeeds, then a `remember_token` is generated (random 60-byte URL-safe string), persisted on the user row, and returned to the client as a `Set-Cookie: remember_<app_key_id>=<token>; HttpOnly; Secure; SameSite=Lax; Max-Age=<configured>`.
- [ ] Given a subsequent request with a valid `remember_<app_key_id>` cookie and no session, when `SessionGuard` resolves, then it logs the user in for the request and rotates the cookie.
- [ ] Given `LoginRequest.remember = False`, when login succeeds, then no remember cookie is set.
- [ ] Given a logged-out user, when logout runs, then the remember cookie is cleared (empty value, `Max-Age=0`).
- [ ] If removed instead: the `remember` field is dropped from `LoginRequest`, the `users.remember_token` column is removed from the auth migration, and tests assert no remnant.
- [ ] Tests cover happy path, no-remember path, logout-clears-cookie, token-rotation-on-use.

**Security Requirements**:
- [ ] Remember token must be high-entropy (≥256 bits), hashed before storage (use the same column-encryption strategy used for sensitive auth tokens), and timing-safe-compared.
- [ ] Token rotation on every successful remember-cookie login (one-time-use semantics) to mitigate cookie theft.
- [ ] Cookie attributes match OWASP guidance: `HttpOnly`, `Secure` in production, `SameSite=Lax`, scoped path/domain.

**Documentation Requirements**:
- [ ] `docs/site/docs/security/authentication.md` documents the remember-me flow if implemented.

**Requirement Refs**: AUDIT-AUTH-CRITICAL-2
**Priority**: Should
**Complexity**: Medium
**Status**: Ready

---

### Story 3: Maintenance `--render` template is rendered

**As a** sysadmin, **I want** `arvel down --render path/to/maintenance.html` to actually serve that template, **so that** the public-facing maintenance page looks like my app.

**Acceptance Criteria**:
- [ ] Given `arvel down --render storage/framework/maintenance.html`, when a non-bypass request hits the app, then the response body is the rendered template (read from disk, served as `text/html` with the configured `Retry-After`).
- [ ] Given a bypass cookie, when the same request hits the app, then it passes through to the app (no template rendering).
- [ ] Given `--render` was passed with a path that doesn't exist when the request lands, then the middleware falls back to the plain-text default and logs an ERROR.
- [ ] Given `--render` was not passed, when a non-bypass request hits, then the existing plain-text default is returned (today's behaviour).
- [ ] Tests cover template-rendered, bypass-cookie, missing-file fallback.

**Security Requirements**:
- [ ] Template path is read from `MaintenanceModeManager` marker — never from request input. No template-injection vector.
- [ ] Set `Cache-Control: no-store` on the maintenance response.

**Documentation Requirements**:
- [ ] `docs/site/docs/digging-deeper/maintenance-mode.md` documents the `--render` flag end-to-end.

**Requirement Refs**: AUDIT-AUTH-IMPORTANT-5
**Priority**: Must
**Complexity**: Small
**Status**: Ready

---

### Story 4: `ArraySessionStore` is registered in `SessionManager`

**As a** test author, **I want** `config('session.driver', 'array')` to actually produce an in-memory store, **so that** session tests don't have to touch the filesystem or a database.

**Acceptance Criteria**:
- [ ] Given `SessionManager._create("array", config)`, when called, then it returns an `ArraySessionStore` instance.
- [ ] Given the array driver, when the test suite finishes, then the store leaves no on-disk residue.
- [ ] Tests cover write/read/forget/flush on the array driver and confirm cross-request isolation when used in tests.

**Security Requirements**:
- [ ] None — array store is for testing only; not registered for production by default.

**Documentation Requirements**:
- [ ] `docs/site/docs/the-basics/session.md` lists `array` among valid drivers with a note that it's test-only.

**Requirement Refs**: AUDIT-AUTH-IMPORTANT-6
**Priority**: Must
**Complexity**: Small
**Status**: Ready

---

### Story 5: Login throttle uses a cache-backed store

**As a** production operator, **I want** login throttling to work across web workers, **so that** an attacker can't bypass the limit by hitting different pods.

**Acceptance Criteria**:
- [ ] Given `ThrottleLoginMiddleware`, when it counts attempts, then it uses `Cache::lock` / `Cache::increment` semantics against the configured cache store (Redis in production), not an in-process dict.
- [ ] Given two concurrent web workers receiving 5 failed logins each for the same user, when the next attempt arrives, then it is throttled (10/5 limit exceeded), not allowed (limit per-worker).
- [ ] Tests cover the shared-state case with a fake Redis (or array cache shared across requests).

**Security Requirements**:
- [ ] Throttle key derived from email + remote IP; both must be normalised before hashing.

**Documentation Requirements**:
- [ ] `docs/site/docs/security/authentication.md` documents the throttle and its cache backend.

**Requirement Refs**: AUDIT-AUTH-IMPORTANT-7
**Priority**: Should
**Complexity**: Small
**Status**: Ready

---

## Dependencies

- Story 5 depends on Story 4 (array store registered) only insofar as test setup uses the array driver; can ship in parallel.
- Stories 1–4 are independent.

## Notes

- Greenfield: per workspace rule, if a field can't be implemented in this sprint, delete it rather than leave it inert.
- The `key:rotate` "tracker ID in user-facing error" issue (audit) is filed separately under `arvel.console.commands.key_rotate` — moved to `WI-007 doc/lint cleanup` because it's process-artifact noise, not a feature.
