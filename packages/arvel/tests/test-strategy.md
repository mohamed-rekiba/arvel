# Test Strategy — WI-arvel-001 (Foundations)

**Author**: QA Engineer (autonomous)
**Date**: 2026-05-17
**PRD**: `docs/prd/PRD-001-foundations.md`

---

## 1. Scope

Validate every functional requirement (FR-001-001 through FR-001-021) and every non-functional requirement (NFR-001-001 through NFR-001-008) for the Arvel framework's Foundations layer.

## 2. Test pyramid

```
                ┌────────────────────────┐
                │  Bench (NFR-001-001/2) │   ← perf gates (Stage 5)
                ├────────────────────────┤
                │  Integration (boot     │   ← Stage 4: full Application lifecycle
                │   lifecycle, FastAPI)  │
                ├────────────────────────┤
                │  Unit (per module)     │   ← Stage 3a (this stage): ~50 tests
                ├────────────────────────┤
                │  Type checks           │   ← every commit (mypy + pyright --strict)
                └────────────────────────┘
```

## 3. Test types

| Type | Tooling | Purpose | Stage |
|---|---|---|---|
| Unit | pytest + pytest-asyncio | Per-module FR coverage | 3a |
| Type-assertion | `typing.assert_type` + mypy + pyright | Public API type contract | 3a + every CI |
| Security unit | pytest | NFR-001-003/004 attack-surface + secret-handling | 3a |
| Integration | pytest + httpx + TestClient | Full app lifecycle + FastAPI bridge end-to-end | 4 |
| Static analysis | bandit + semgrep + pip-audit + gitleaks | Stage 4b | 4b |
| Benchmarks | pytest-benchmark | NFR-001-001/002 perf budgets | 5 (nightly) |
| Smoke | `arvel new tmp` | Skeleton boots without error | 5 |

## 4. Coverage targets

- Unit coverage on `packages/arvel/src/arvel`: ≥ 90% (target 95%).
- Per-module floor: every module under `arvel/container`, `arvel/application`, `arvel/providers`, `arvel/config`, `arvel/support` ≥ 85%.
- Branch coverage enabled.
- `tests/` itself excluded.

## 5. Red state at QA-Pre exit (this stage)

All tests fail. Failure mode is one of:
- `ImportError` (the module/class/symbol doesn't yet exist).
- `AttributeError` (the method/attribute doesn't yet exist).
- `AssertionError` (the symbol exists as a stub but doesn't yet behave correctly).

Per TDD discipline:
- No test is skipped to make CI pass.
- Coverage is measured but the 90% threshold is **not** enforced at QA-Pre exit — only at QA-Post.

## 6. Green path (Stage 3b)

Developer implements code to drive every test to GREEN, in the order:
1. `arvel.support.env` → `test_env.py`
2. `arvel.support.{pipeline,collections}` → respective tests
3. `arvel.config.{settings,registry,repository,errors}` → config tests
4. `arvel.container.*` → container tests (basic → autowire → contextual → tagging → extending → scopes → async → bridge)
5. `arvel.providers.*` → service provider + config provider tests
6. `arvel.application.*` → application tests
7. `arvel/__init__.py` re-exports + `dep` helper → public API tests

## 7. CI integration

Local `make verify` and CI `.github/workflows/ci.yml` run the same gates:
- `make test` (pytest + coverage)
- `make typecheck` (mypy + pyright)
- `make lint`
- `make security`

## 8. Out of scope (deferred to later WIs)

- HTTP route handler tests (WI-arvel-002)
- ORM query tests (WI-arvel-003)
- Queue worker tests (WI-arvel-007)
- All other facade tests (per their respective WIs)
