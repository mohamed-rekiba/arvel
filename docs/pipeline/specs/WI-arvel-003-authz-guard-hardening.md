# WI-arvel-003 — Authorization guard hardening (no privilege escalation, no redundant fetch)

| | |
|---|---|
| **Module** | auth / permission |
| **Complexity** | L2 | **Risk** | Tier 3 (authz change) | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/003-auth-permission.md` (F1, F2) |
| **Review** | `requesting-code-review` — F1 escalation HIGH (3 controller methods); F2 redundant user fetch (N+1) confirmed |

## Problem

**F1 — privilege escalation (HIGH, OWASP A01).** In the kit's `AdminUsersController`,
`grant_permission`, `revoke_permission`, and `revoke_role` gate only on
`require_permission(request, "roles.manage")`. They never check the **actor's** own
authority against the thing being changed:

- `grant_permission` / `revoke_permission` let a `roles.manage` holder grant/revoke
  **any** permission, including ones the actor does not hold → escalation.
- `revoke_role` skips the `actor.has_level(role_level)` check that the sibling
  `assign_role` already performs → a lower-level admin can revoke a role above their
  level.

**F2 — redundant user fetch (N+1).** `make_permission_guard` calls `require_auth`
(which already loads the configured user via `me() → user_cls.find()`), then issues a
**second, identical** `SELECT` to reload the same row by id. The kit wires the guard with
the same `User` class the auth service is configured with, so the reload returns the same
object it already had — one wasted round-trip on every permission-checked request.

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | `grant_permission` denies (403) when the actor does **not** hold the permission being granted; proceeds when they do. | `test_057_authz_escalation_guard.py::test_grant_permission_*` | PASS |
| SPEC-2 | `revoke_permission` denies (403) when the actor does **not** hold the permission being revoked. | `::test_revoke_permission_blocks_when_actor_lacks_permission` | PASS |
| SPEC-3 | `revoke_role` denies (403) when the actor's level is below the target role's level (parity with `assign_role`). | `::test_revoke_role_*` | PASS |
| SPEC-4 | `make_permission_guard` issues **no** second user query when `me()` already returns an instance of the guard's `user_model`; still reloads when `me()` returns a different type (existing fakes). | `test_guards.py::TestPermissionGuard::test_no_redundant_query_when_me_returns_user_model`, `::test_reloads_when_me_returns_other_type` | PASS |
| SPEC-5 (X-cut: behavior) | All existing auth guard / role-level behavior preserved (permission held/missing/not-found, level met/too-low). | `test_guards.py` (full, green) | PASS |
| SPEC-6 (X-cut: type safety) | mypy --strict + pyright clean; no new `# type: ignore` / `cast`-to-`Any` / `Any` at public boundaries. | `mypy` + `pyright` | PASS |
| SPEC-7 (X-cut: no regression) | arvel auth suite + kit unit suite stay green; ruff clean. | `pytest` + `ruff check` | PASS |

## Root-cause fixes

- `arvel/auth/guards/__init__.py` — `make_permission_guard`: use the user returned by
  `require_auth` directly when it is already an instance of `user_model`; only fall back
  to a reload when the auth service is wired with a different model. Removes the
  always-on second query without dropping the safety reload for mismatched configs.
- `kits/.../app/http/controllers/admin/users.py`:
  - `grant_permission` / `revoke_permission`: after `require_permission(..., "roles.manage")`,
    require `await actor.has_permission_to(<perm>)`; else `AuthorizationException`.
  - `revoke_role`: look up the role level and require `await actor.has_level(level)`,
    mirroring `assign_role`; else `AuthorizationException`.

## Deliberate design decisions

- **Coherent authority rule:** "you can only grant/revoke permissions you hold, and only
  manage roles at or below your level." This makes the four mutation methods (`assign_role`,
  `revoke_role`, `grant_permission`, `revoke_permission`) consistent, and matches how
  Laravel apps gate spatie's `givePermissionTo` behind a Policy — the package supplies the
  primitive, the app enforces the policy.
- **`isinstance` fast path, not param removal:** keeping `user_model` and gating the reload
  on `isinstance` preserves correctness when an app wires the auth service and the guard
  with different models, and keeps the existing guard tests (whose `me()` returns a
  `SimpleNamespace`) meaningful.

## Deferred (tracked, not silent-corrupting)

- **F3** — `has_permission_to` calls `permissions.all()` per role (N+1 across roles).
  `arvel_permission` performance WI.
- **F4** — `password_resets` migration/model column drift. Dedicated auth-flow WI.
- **F5** — access JWT has no revocation denylist; login throttle is process-local.
  Needs threat-model + storage decision; separate WI.
- **F6** — `auth/provider._mount_routes` captures a controller at boot (same shape as
  WI-002 D1). Kit binds its auth controller via `instance()` (stateless), so no active
  bleed. Separate fix in this module.
