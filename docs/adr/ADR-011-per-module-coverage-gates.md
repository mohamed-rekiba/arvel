# ADR-011 — Per-module coverage gates (promoted from FB-010)

**Status**: Accepted
**Date**: 2026-05-17
**Last reconciled**: 2026-06-01
**Implements**: FB-010 (from ops report)

## Context

The WI-001 and WI-002 ops reports both flagged that an aggregate
`--cov-fail-under=90` over the entire package can mask a low-coverage
new module by averaging it with high-coverage existing modules. Concretely:
the WI-002 HTTP layer landed at 92.96% aggregate, but if a future PR added
a 60%-covered `arvel.database` and the overall stayed at 90% via the
high-covered foundations, we'd ship a broken ORM.

Three options:

| Option | Pros | Cons |
|---|---|---|
| A. Keep aggregate only, raise the floor to 95% | Simplest | Still allows a single bad module to slip through if siblings compensate |
| B. Aggregate + per-module gates configured per-package-area | Catches both regressions | One config knob per module to maintain |
| C. **Per-module gates only (no aggregate)** | Most precise; impossible to mask | More config; raises the floor for every module |

## Decision

Option B (aggregate + per-module). The aggregate gate stays at 90% as a
backstop. Per-module floors live in `pyproject.toml` under
`[tool.coverage.arvel_per_module]` and are pinned just below the current
measured numbers so refactors don't get blocked, and raised whenever real
coverage climbs durably.

```toml
[tool.coverage.report]
fail_under = 90              # aggregate backstop

[tool.coverage.arvel_per_module]
"arvel.application" = 93.0
"arvel.config"      = 95.0
"arvel.container"   = 90.0
"arvel.database"    = 92.0
"arvel.facades"     = 100.0
"arvel.http"        = 92.0
"arvel.providers"   = 80.0   # database_provider boot/shutdown is partially mocked; raise as integration grows
"arvel.routing"     = 92.0
"arvel.support"     = 90.0
```

The enforcement is a workspace-root `conftest.py` that hooks
`pytest_terminal_summary` (read the per-module numbers, print a section) and
`pytest_sessionfinish` (promote any breach to a non-zero exit). This was
chosen over a standalone plugin because the conftest is auto-discovered by
pytest and ships with the workspace, with no extra `pytest_plugins`
indirection.

## Consequences

**Positive**:
- Impossible for a new low-coverage module to slip in under cover of
  high-coverage siblings.
- Per-module section appears as part of the standard `pytest --cov` run, so
  CI logs are self-explanatory:

  ```
  ================= Per-module coverage gates (FB-010 / ADR-011) =================
    arvel.database                                      93.95% (floor 92.00%) OK
    arvel.providers                                     85.71% (floor 80.00%) OK
    …
  ```
- One-line floor changes in `pyproject.toml`; no plugin code to redeploy.

**Negative**:
- Adding a new top-level module requires adding a row. Until then it's
  governed only by the aggregate floor. Mitigated by the visibility of the
  new section in CI output and by the fact that the conftest prints
  `[SKIP — no measured files]` for unmatched entries, making typos obvious.
- A second source of truth for "what counts as a module" (the dotted module
  name in the table vs. file layout under `packages/arvel/src/arvel/`). The
  conftest matches on path prefix so the two are kept in sync naturally.

**Enforcement**:
- `make coverage` (or any `pytest --cov` run) prints the per-module section
  and fails the run on any breach.
- The aggregate `fail_under = 90` remains as a backstop.

## Current implementation

- Floors: root `pyproject.toml` `[tool.coverage.arvel_per_module]` (still the
  nine modules and values quoted above).
- Enforcement: workspace-root `conftest.py` (`pytest_terminal_summary` +
  `pytest_sessionfinish`).
- Docs: `docs-fresh/contributing/quality-gates.md`.
