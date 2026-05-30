# ADR-003 — Monorepo with `uv` workspaces, skeleton auto-split

**Date**: 2026-05-17
**Status**: Accepted
**Deciders**: Solution Architect (autonomous), Product Engineer (proposer)
**Scope**: Whole repository layout

---

## Context


1. **Polyrepo** (Laravel's approach in PHP/Composer): each thing in its own repo, framework internally monorepo'd then auto-split.
2. **Monorepo** with workspace tooling: one repo, multiple packages, one lockfile, atomic cross-package changes.

In Python 2026, the `uv` ecosystem has first-class workspace support; in 2013 PHP, it didn't.

## Options considered

### Option A — Polyrepo like Laravel

**Pros**: Smaller per-repo surface; community fork-friendly per package; mature pattern.
**Cons**:
- Adding a feature that needs framework + skeleton changes = two coordinated PRs.
- CI duplicated 3+ times.
- Issue tracking fragmented.
- Refactor pain for breaking changes.
- During 0.x (rapid iteration), this is significant friction.

### Option B — Pure monorepo, no auto-split (chosen for dev, augmented for users)

**Pros**: Atomic cross-package PRs; one CI; one lock file; one issue tracker; refactor-friendly.
**Cons**: External users want to clone "just the skeleton" without the framework dev clutter.

### Option C — Monorepo + auto-split (chosen)

**Pros**: Combine the best of both — monorepo DX for us, polyrepo UX for users. Skeleton lives in `skeleton/` and is auto-pushed to `github.com/arvel/skeleton` on every tag via `git subtree split`. Installer downloads from there.

**Cons**: One extra CI step (~10 seconds); one external repo to monitor.

## Decision

**Option C.** Per `REPO-STRUCTURE.md`:

- Single GitHub repo `github.com/arvel/arvel`.
- `tool.uv.workspace.members = ["packages/*"]` with `packages/arvel/` + `packages/arvel-cli/`.
- `skeleton/` lives in this repo and is auto-split to a public template repo via `tools/split-skeleton.sh` in `.github/workflows/release.yml`.
- One `uv.lock` at repo root; shared dev tooling (ruff, mypy, pyright, pytest, pre-commit) at root.
- Per-package `pyproject.toml` declares the package's own deps; dev-time cross-package refs use `tool.uv.sources.<pkg> = { workspace = true }`.

## Consequences

- CI complexity goes up slightly (one matrix per workspace member) but `uv` handles caching natively.
- Versioning rule: during 0.x, the three artifacts (framework, cli, skeleton) cut as one release train. Post-1.0 they can diverge.
- Future first-party companions (Sanctum-eq, Horizon-eq, …) start as modules inside `packages/arvel/`. Only graduate to their own workspace member when surface or release cadence diverges.

## References

- `docs/REPO-STRUCTURE.md` (full layout, release flow, CI matrix).
- Laravel's auto-split via `splitsh/lite`: https://github.com/splitsh/lite.
- uv workspaces: https://docs.astral.sh/uv/concepts/workspaces/
