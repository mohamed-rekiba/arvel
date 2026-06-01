# ADR-004 — Single `arvel` package with optional extras; companions as separate distributions

**Status**: Accepted (revised — see Notes)
**Date**: 2026-05-17
**Last reconciled**: 2026-06-01
**Deciders**: Solution Architect (autonomous)
**Scope**: PyPI distribution surface

---

## Context

Laravel ships ~30 first-party packages, each installable independently, held together by Composer's metadata graph. Python's equivalent question: ship `arvel-container`, `arvel-orm`, `arvel-queue`, … or one `arvel` with optional extras?

## Options considered

### Option A — One package per subsystem (Laravel pattern)

**Pros**: install only what you use. **Cons**: 30+ lock-step releases; awkward cross-package imports in Python; harder type stubs and circular-dep avoidance; poor discoverability; multiplies coordination cost at 0.x.

### Option B — Single `arvel` package with optional extras (chosen for core)

**Pros**: `pip install arvel[redis,postgres,queue]` mirrors Laravel UX; core code lives together under one import path and one `__all__`; one release artifact, CHANGELOG, and upgrade guide; refactor-friendly. **Cons**: all optional-import paths land in site-packages (small disk cost, no runtime cost — driver modules lazy-import); requires discipline on extras boundaries (enforced by import-error tests).

### Option C — Hybrid: split major subsystems when real demand emerges

Considered for post-1.0; partially realized already via the companion packages below.

## Decision

The **core framework ships as a single `arvel` package** with optional extras for drivers. **Self-contained companions ship as their own PyPI distributions** and are surfaced as extras on `arvel`. There is no separate `arvel-cli` package — the CLI binary ships inside `arvel`.

Driver/integration extras on `arvel` (from `packages/arvel/pyproject.toml`):

`bcrypt`, `redis`, `postgres`, `mysql`, `sqlite`, `queue`, `queue-redis`, `queue-amqp`, `mail`, `s3`, `gcs`, `azure`, `jwt`, `broadcasting`, `shell`, `openapi`, `dev`.

Companion-package extras (each pulls a separate distribution):

`permission` → `arvel-permission`, `image` → `arvel-image`, `image-heif` → `arvel-image[heif]`, `oauth` → `arvel-oauth`, `search` → `arvel-search`, `audit` → `arvel-audit`.

`arvel[all]` aggregates everything.

## Consequences

- Driver modules lazy-import with a clear `ImportError` pointing at the extra to install (e.g. "install `arvel[redis]`").
- Each extra has a driver-availability test; CI installs all extras.
- Companions depend on `arvel` but version and release on their own track.

## Current implementation

- Extras: `packages/arvel/pyproject.toml` (`[project.optional-dependencies]`).
- Companions: `packages/arvel-*`; docs at `docs-fresh/packages/overview.md`.

## Notes

- **Revised from the original**: the original ADR specified exactly two packages (`arvel` + `arvel-cli`). The CLI was folded into the `arvel` binary (ADR-126, ADR-126), and several subsystems graduated to standalone companion distributions (`arvel-audit`, `arvel-image`, `arvel-oauth`, `arvel-permission`, `arvel-search`). The core principle — single core package, drivers as extras — holds.
- The original `mail-ses` / `mail-resend` / `auth-jwt` / `auth-oauth` / `storage-*` extra names were consolidated into the current set above.
