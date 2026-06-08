# Epic: Authorization guard hardening

## Summary
Close two authorization-path defects: a privilege-escalation gap in the kit's admin
role/permission management, and a redundant per-request user query in the framework's
permission guard. Together they make the authorization path both safe (no escalation) and
lean (one user load per request).

**Module:** auth / permission · **Spec:** `docs/pipeline/specs/WI-arvel-003-authz-guard-hardening.md`

## Stories

### Story 1: No privilege escalation when managing permissions
**As a** platform operator, **I want** an admin to be able to grant or revoke only the
permissions they themselves hold, **so that** a user with `roles.manage` cannot escalate
their own (or someone else's) abilities beyond what they were granted.

**Acceptance Criteria**:
- [x] Given an actor who does **not** hold permission `P`, when they call grant-permission for `P`, then the request is denied (403) and nothing is granted.
- [x] Given an actor who **does** hold `P`, when they call grant-permission for `P`, then the escalation gate passes and normal handling continues.
- [x] Given an actor who does **not** hold permission `P`, when they call revoke-permission for `P`, then the request is denied (403).

**Security Requirements**:
- [x] Mutating RBAC primitives (`give_permission_to` / `revoke_permission_to`) are gated by an actor-holds-permission check at the controller boundary (OWASP A01).

**Documentation Requirements**:
- [x] `docs/site/docs/packages/permission.md` warns that the RBAC trait methods are primitives and the app must enforce "grant only what you hold; manage only roles at/below your level".

**Requirement Refs**: SPEC-1, SPEC-2
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: No role-level bypass when revoking roles
**As a** platform operator, **I want** revoking a role to require the actor to outrank that
role, **so that** a lower-level admin cannot strip a role above their level — matching the
existing check on role assignment.

**Acceptance Criteria**:
- [x] Given an actor whose level is below the target role's level, when they revoke that role, then the request is denied (403).
- [x] Given an actor whose level is at or above the target role's level, when they revoke that role, then the level gate passes and normal handling continues.

**Security Requirements**:
- [x] `revoke_role` enforces the same `has_level` check as `assign_role`.

**Documentation Requirements**:
- [x] Covered by the Story 1 doc warning.

**Requirement Refs**: SPEC-3
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 3: One user load per permission check
**As a** developer, **I want** the permission guard to reuse the user already resolved from
the token, **so that** every permission-checked request doesn't issue a second identical
`SELECT` for the same user.

**Acceptance Criteria**:
- [x] Given `me()` returns an instance of the guard's configured user model, when the guard runs, then it issues no additional user query and checks the permission on that user.
- [x] Given `me()` returns a different type than the guard's model, when the guard runs, then it falls back to a typed reload (existing behavior preserved).

**Security Requirements**:
- [x] None — behavior-preserving optimization; the suspension/auth checks in `me()` still run.

**Documentation Requirements**:
- [x] None (internal guard behavior; no public API change).

**Requirement Refs**: SPEC-4, SPEC-5
**Priority**: Should · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001 (ORM) and WI-arvel-002 (controllers).

## Notes
- Deferred follow-ups (separate work items):
  - **F3** — `has_permission_to` calls `permissions.all()` per role (N+1 across roles);
    `arvel_permission` performance WI.
  - **F4** — `password_resets` migration/model column drift; dedicated auth-flow WI.
  - **F5** — access JWT has no revocation denylist; login throttle is process-local;
    needs a threat model + storage decision.
  - **F6** — `auth/provider._mount_routes` captures a controller at boot (same shape as
    WI-002 D1); kit binds its auth controller via `instance()`, so no active bleed.
  - **F7** — monorepo test-harness quirk: pytest's prepend mode inserts the workspace root
    ahead of the kit backend, so a bare `import config` resolves to the workspace `config`
    package and breaks ~33 kit unit tests that import `app.*` at runtime. Pre-existing and
    unrelated to auth; WI-003's new test works around it with a contained loader. Worth its
    own test-infra WI (e.g. `--import-mode=importlib` for the kit, or renaming a package).
