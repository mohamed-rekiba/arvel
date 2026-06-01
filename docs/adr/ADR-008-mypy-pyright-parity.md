# ADR-008 — Enforce both `mypy --strict` and `pyright --strict` (parity required)

**Status**: Accepted
**Date**: 2026-05-17
**Last reconciled**: 2026-06-01
**Deciders**: Solution Architect (autonomous), constitutional baseline
**Scope**: Whole framework (constitution Article II)

---

## Context

Type-safety is a stated product feature of Arvel. Python has two production-grade strict checkers: **mypy** (canonical, broad editor/CI presence) and **pyright** (Microsoft's, faster, default in Pylance/Cursor, slightly stricter). A strict-type-safety promise is hollow if it depends on which checker the user runs.

## Options considered

### Option A — Only `mypy --strict`

**Pros**: single tool, canonical PEP reference. **Cons**: pyright/Pylance users (the majority of VS Code/Cursor population) hit errors we never tested for.

### Option B — Only `pyright --strict`

**Pros**: faster, matches the most popular editor experience. **Cons**: code not provably correct under mypy, which runs in many CI pipelines.

### Option C — Both, parity required (chosen)

**Pros**: the effective floor is the stricter of the two; editor experience matches CI for both populations; forces code that's clear to both tools. **Cons**: two CI jobs (run in parallel); occasional divergence (handled by satisfying the stricter side); slightly slower local `make typecheck`.

## Decision

**Option C.** Both checkers run in CI and in `make typecheck`, both in strict mode with no relaxations beyond the strict baseline. On divergence, the build fails on whichever tool reports an issue and the code is fixed. Suppressions are governed by ADR-009 (zero-warning policy) and ADR-010 (the irreducible suppression floor for dual-checker disagreements).

## Consequences

- Public APIs are fully type-annotated from the first commit.
- Container resolution (`make[T] -> T`) is designed to be inferable by both checkers.
- Generic-heavy modules (Container, QueryBuilder, Pipeline) are designed types-first.
- mypy is the slower of the two and is the typecheck CI bottleneck.

## Current implementation

- Config: `packages/arvel/pyproject.toml` (`[tool.mypy]`, `[tool.pyright]`), root `pyproject.toml`.
- Gates: `make typecheck` (runs `uv run mypy` and `uv run pyright`); `.pre-commit-config.yaml`; `.github/workflows/ci.yml` typecheck job.
- Docs: `docs-fresh/contributing/quality-gates.md`.

## References

- mypy strict: https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-strict
- pyright strict: https://microsoft.github.io/pyright/#/configuration
- ADR-009 (zero-warning policy), ADR-010 (suppression floor).
