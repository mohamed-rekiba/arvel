# ADR-010 — Adopt mkdocs-material now; auto-generate API reference from docstrings

**Date**: 2026-05-17
**Status**: Accepted
**Deciders**: Solution Architect (autonomous)
**Scope**: `docs/site/`, CI

---

## Context

Foundations shipped without a published docs site (FB-004). The constitution (Article V) lists `mkdocs build --strict` as a CI gate that was deferred to post-Phase-11. The HTTP layer adds ~30 public symbols on top of the foundations' 18; a published reference becomes valuable now, not later.

## Decision

Bootstrap a `mkdocs-material` site from WI-002. Two pillars:

1. **Hand-written narrative docs** under `docs/site/` — install, quickstart, container, providers, config, routing, controllers, form-requests, resources, middleware, auth, throttle, csrf, exceptions. One page per concept.
2. **Auto-generated API reference** via `mkdocstrings` (Python handler) — renders type signatures + docstrings for every public symbol under `arvel.*`. No hand-maintained reference table.

`mkdocs.yml` lives at repo root. `mkdocs build --strict` is a CI gate from this WI onwards.

## Why now (override the deferral)

- Public surface is non-trivial after WI-002. The longer we wait, the more docstring debt.
- `mkdocstrings` paired with our strict typing means the reference is always in sync — adding the gate now prevents drift.
- The constitution already lists this gate; we're moving the activation date in, not adding a new gate.
- FB-004 was scoped as "low priority" only because foundations had a small surface; the cost-benefit flips at HTTP scale.

## Why mkdocs-material

- Best-in-class search out of the box.
- First-class `mkdocstrings` integration.
- Themable to match Laravel-style docs visually.
- Mature, single-vendor (Squidfunk), strong release cadence.

Alternatives considered:
- **Sphinx**: more powerful but heavier; reStructuredText hostile to drive-by contributors.
- **Docusaurus**: forces a Node toolchain into a Python-only repo.

## Trade-offs

- One more CI gate to fail on (`mkdocs build --strict`).
- Docstring discipline becomes mandatory (was already constitution Article IX.1 — this enforces it).
- A new dev-time tool (`uv add --group docs mkdocs-material mkdocstrings[python]`).

## Consequences

- Adds `docs` dependency group in `pyproject.toml` (root + arvel package).
- New `make docs-serve` and `make docs-build` targets.
- New CI job `docs` (parallel with lint/typecheck/test).
- Hosting: GitHub Pages from the `gh-pages` branch (set up post-publish, not gating this WI).

---

## Cross-references

- PRD-002: FR-002-028, NFR-002-006
- Constitution Article V (`mkdocs build --strict` gate)
- Backlog item: FB-004
