# ADR-090 — Auth subsystem ownership: kit → framework

**Date**: 2026-05-21
**Status**: Accepted
**Context**:
**Supersedes**: nothing
**Superseded by**: nothing

---

## Context

produced the fullstack-Vue starter kit, but built the
authentication subsystem (~1,789 LOC) inside the kit's `backend/app/`
directory rather than the framework's `arvel.auth` module. The user's review
of WI-027 highlighted this as a fundamental architectural mistake:

> The authentication system should be a core part of the framework itself,
> not implemented in the template/kit.

This ADR records the decision to move the subsystem and the rationale.

## Decision

Authentication — register, login, logout, refresh-token rotation, email
verification, forgot/reset password, the controller, the routes, the
mailables, the templates, the listeners, the throttling — moves from
`packages/arvel-starter-fullstack-vue/backend/app/` into
`packages/arvel/src/arvel/auth/` (the framework).

The kit becomes a **consumer** of `arvel.auth`. It overrides what it needs to
override (mailable styling, audit listener for cross-cutting business audit,
error-page redirects), nothing more.

## Drivers

1. **Constitution Article II §4 — Laravel mental model is preserved.** Laravel's
   auth ships in `illuminate/auth`, not in every Laravel app's `App\Auth`
   directory. Arvel must preserve this.
2. **Reuse.** Every Arvel app needs auth. Per-app reimplementation is a
   YAGNI violation in reverse — every consumer pays the implementation
   cost over and over.
3. **Security audit surface.** Auth code is the highest-risk module in any
   web framework. Centralising it in `arvel.auth` means one auditable place
   instead of N kit-derived copies.
4. **Override hooks.** Frameworks need extension points; this WI defines them
   via container bindings + publishable assets, matching Laravel's
   `AuthServiceProvider` shape.

## Alternatives considered

### A. Keep auth in the kit, ship a "starter pack" mindset (status quo)

**Pros**:
- Zero migration work.
- App author can edit any line without thinking about overrides.

**Cons**:
- Constitution Article II §4 violated.
- Every kit ships with its own auth → divergence over time.
- Security fixes can't be pushed centrally; users must merge upstream changes by hand.

**Rejected**: violates the constitution.

### B. Auth as a separate `arvel-auth` PyPI package

**Pros**:
- Clean module boundary.
- Auth can version independently from the core.

**Cons**:
- Constitution Article III §1 mandates a modular monolith until 1.0.
- Splitting is premature optimisation (no real-world signal demands it).

**Rejected**: defer to post-1.0.

### C. Move auth into framework but keep it opt-in (provider not registered by default)

**Pros**:
- API-only apps that don't need auth pay nothing.

**Cons**:
- Confuses the mental model (Laravel always has the `Auth` facade available).
- Tree-shaking isn't a real concern in Python.
- Default-on with `config.auth.routes.enabled=false` opt-out is a better escape.

**Rejected**: chose default-on with config opt-out.

## Consequences

### Positive

- ~1,789 LOC removed from the kit (lighter starter).
- Single auditable auth implementation in the framework.
- Consistent mental model — every Arvel app uses the same auth shape.
- FB-027-007/008/011/012 closed by this WI.

### Negative

- ~3,000 LOC added to `arvel.auth` (gross addition; coverage gate
  applies — must stay ≥90 % to land).
- Migration sub-sprint (S25.4) requires breaking the kit transiently.
- Any kit-side auth customisation (e.g. branded email) must now be done via
  publish + override, not "edit the source in place".

### Neutral

- The `password_resets` table moves from kit-owned migration to framework
  publishable. Existing kit-deployed databases keep their existing rows;
  `vendor:publish` no-ops because the table already exists.

## Implementation

See SAD-028 (`docs/architecture/SAD-028-arvel-auth-core.md`)

## Validation

- All FRs FR-028-01..49 in PRD-028 pass acceptance.
- `arvel.auth` clean under `mypy --strict` and `pyright --strict`.
- Coverage ≥90 % on the new modules.
- Kit's full integration suite green after the migration commit.
