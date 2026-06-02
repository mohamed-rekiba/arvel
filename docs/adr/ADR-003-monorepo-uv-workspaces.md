# ADR-003 — Monorepo with `uv` workspaces

**Status**: Accepted (skeleton-distribution mechanism superseded — see Notes)
**Date**: 2026-05-17
**Last reconciled**: 2026-06-01
**Deciders**: Solution Architect (autonomous), Product Engineer (proposer)
**Scope**: Whole repository layout

---

## Context

Two repository shapes were available: polyrepo (Laravel's PHP/Composer approach — each thing in its own repo, auto-split from an internal monorepo) versus a monorepo with workspace tooling (one repo, multiple packages, one lockfile, atomic cross-package changes). In Python 2026 `uv` has first-class workspace support, which 2013-era PHP lacked.

## Options considered

### Option A — Polyrepo like Laravel

**Pros**: smaller per-repo surface, fork-friendly per package. **Cons**: cross-cutting features need coordinated PRs; CI duplicated; fragmented issues; painful refactors during 0.x rapid iteration.

### Option B — Pure monorepo

**Pros**: atomic cross-package PRs, one CI, one lockfile, one issue tracker, refactor-friendly. **Cons**: external users want "just the skeleton" without dev clutter.

### Option C — Monorepo (+ generated skeleton) — chosen

**Pros**: monorepo DX for maintainers, clean project-generation UX for users. **Cons**: one extra generation/packaging step.

## Decision

**Monorepo with `uv` workspaces.** `tool.uv.workspace.members = ["packages/*", "kits/*"]`. One `uv.lock` at the repo root; shared dev tooling (ruff, mypy, pyright, pytest, pre-commit) configured at root. Per-package `pyproject.toml` declares each package's own dependencies; cross-package dev refs use `tool.uv.sources.<pkg> = { workspace = true }`. Companion libraries live under `packages/`; starter kits (reference apps scaffolded by `arvel new --kit`) live under `kits/`.

Current workspace members:

| Member | Location | Role |
|---|---|---|
| `arvel` | `packages/` | The framework (ships the `arvel` CLI binary) |
| `arvel-audit` | `packages/` | Audit-log companion |
| `arvel-image` | `packages/` | Image manipulation companion |
| `arvel-oauth` | `packages/` | OAuth/social-login companion |
| `arvel-permission` | `packages/` | Roles & permissions companion |
| `arvel-search` | `packages/` | Full-text / engine-backed search companion |
| `arvel-ecommerce-kit` | `kits/` | Reference application + `--kit ecommerce` source (not published) |

## Consequences

- CI runs across workspace members; `uv` handles caching natively.
- During 0.x the framework and companions iterate together; post-1.0 they can diverge on cadence.
- New first-party companions start as their own `packages/*` member when surface or release cadence justifies it.

## Current implementation

- Layout: `packages/*` (companion libraries), `kits/*` (starter kits), root `pyproject.toml` (`[tool.uv]`), `uv.lock`.
- Docs: `docs-fresh/contributing/repo-and-build.md`, `docs-fresh/packages/overview.md`.

## Notes

- **Superseded mechanism**: the original ADR specified a separate `arvel-cli` workspace member and an external `skeleton/` repo auto-split via `git subtree`. Neither exists today. The CLI was consolidated into the single `arvel` binary (ADR-126, ADR-126), and the project skeleton is packaged inside `arvel` (`packages/arvel/src/arvel/_skeleton/`) and rendered by `arvel new`. The monorepo + `uv` workspace decision itself still holds.
