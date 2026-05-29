# ADR-005 — Enforce both `mypy --strict` and `pyright --strict` (parity required)

**Date**: 2026-05-17
**Status**: Accepted
**Deciders**: Solution Architect (autonomous), constitutional baseline
**Scope**: Whole framework (constitution Article II)

---

## Context

Type-safety is a stated product feature of Arvel (constitution Article II). Python has two production-grade strict type checkers:

- **mypy** — the original; defacto standard; runs in many editors; PEP-695 / PEP-749 support catching up.
- **pyright** — Microsoft's; faster; default in Pylance (VS Code); slightly stricter; more bleeding-edge PEP support.

A strict-type-safety promise is hollow if it depends on which checker the user runs.

## Options considered

### Option A — Only `mypy --strict`

**Pros**: Single tool to satisfy; canonical PEP reference; richer plugin ecosystem.
**Cons**: Pyright/Pylance users (the majority of VS Code/Cursor population) get inferior in-editor type info if we haven't tested against pyright. They'll hit errors we don't.

### Option B — Only `pyright --strict`

**Pros**: Faster; same engine as the most popular editor experience.
**Cons**: We'd ship code that's not provably correct under mypy, which is what runs in many existing CI pipelines. Adoption friction for teams standardized on mypy.

### Option C — Both, parity required (chosen)

**Pros**:
- Either tool finds an issue → we fix it. Effective minimum is the strictest of the two.
- Editor experience for both VS Code/Cursor (pyright) and PyCharm/community-mypy users is consistent with CI.
- Forces us to write the kind of code that's clear to *both* tools — typically cleaner.

**Cons**:
- Two CI jobs (we run them in parallel).
- Occasional divergence (one tool accepts what the other rejects) — handled by always satisfying the stricter side.
- Slightly slower local `make typecheck`.

## Decision

**Option C.**

- CI runs both, in parallel, per workspace member.
- Local `make typecheck` runs both.
- On divergence: the build fails on whichever tool reports an issue. We fix the code. We do NOT add per-tool ignore comments without documenting the divergence (see `docs/dx/quality-gates.md` § Waivers).
- Configuration:
  - `mypy --strict` with no relaxations beyond the strict baseline.
  - `pyright --strict` with no relaxations beyond the strict baseline.
- We use **stub snapshot tests** for the public API: a `tests/test_stubs.py` invokes both checkers in subprocess against a representative usage script and diffs the output against committed snapshots.

## Consequences

- We commit to writing fully type-annotated public APIs from commit 1 — no `# type: ignore` without justification.
- Container resolution (`make[T] -> T`) must be inferable by both — possibly with `Self`-returning helpers and `overload`s where needed.
- Generic-heavy modules (Container, QueryBuilder, Pipeline) are designed *test-types-first* (typing tests written before the implementation).
- Performance: pyright is roughly 5–10× faster than mypy on this codebase; the bottleneck of the typecheck CI step is mypy.

## References

- mypy: https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-strict
- pyright: https://microsoft.github.io/pyright/#/configuration?id=type-check-rule-overrides
- assert_type (PEP 647 + 3.11+): https://docs.python.org/3/library/typing.html#typing.assert_type
- Stub snapshot pattern (inspired by pyright's own test suite): https://github.com/microsoft/pyright/tree/main/packages/pyright-internal/src/tests
