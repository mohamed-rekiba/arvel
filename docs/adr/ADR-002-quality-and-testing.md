# ADR-002 — Quality & Testing

**Status**: Accepted
**Date**: original decisions 2026-05-17 – 2026-05-23; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: Type-checker parity, gate enforcement policy, suppression-floor strategy, per-module coverage, the testing app fixture.

## Why this is one ADR

All five decisions establish how the project enforces correctness — type checks, lint gates, coverage, and the testing harness — so they share one rationale and one set of consequences.

---

## § 1 — Enforce both `mypy --strict` and `pyright --strict` (parity required)

**Originally**: ADR-008 · Date: 2026-05-17

### Context

Type-safety is a stated product feature of Arvel. Python has two production-grade strict checkers: **mypy** (canonical, broad editor/CI presence) and **pyright** (Microsoft's, faster, default in Pylance/Cursor, slightly stricter). A strict-type-safety promise is hollow if it depends on which checker the user runs.

### Options considered

#### Option A — Only `mypy --strict`

**Pros**: single tool, canonical PEP reference. **Cons**: pyright/Pylance users (the majority of VS Code/Cursor population) hit errors we never tested for.

#### Option B — Only `pyright --strict`

**Pros**: faster, matches the most popular editor experience. **Cons**: code not provably correct under mypy, which runs in many CI pipelines.

#### Option C — Both, parity required (chosen)

**Pros**: the effective floor is the stricter of the two; editor experience matches CI for both populations; forces code that's clear to both tools. **Cons**: two CI jobs (run in parallel); occasional divergence (handled by satisfying the stricter side); slightly slower local `make typecheck`.

### Decision

**Option C.** Both checkers run in CI and in `make typecheck`, both in strict mode with no relaxations beyond the strict baseline. On divergence, the build fails on whichever tool reports an issue and the code is fixed. Suppressions are governed by ADR-002 § 2 (zero-warning policy) and ADR-002 § 3 (the irreducible suppression floor for dual-checker disagreements).

### Consequences

- Public APIs are fully type-annotated from the first commit.
- Container resolution (`make[T] -> T`) is designed to be inferable by both checkers.
- Generic-heavy modules (Container, QueryBuilder, Pipeline) are designed types-first.
- mypy is the slower of the two and is the typecheck CI bottleneck.

### Current implementation

- Config: `packages/arvel/pyproject.toml` (`[tool.mypy]`, `[tool.pyright]`), root `pyproject.toml`.
- Gates: `make typecheck` (runs `uv run mypy` and `uv run pyright`); `.pre-commit-config.yaml`; `.github/workflows/ci.yml` typecheck job.
- Docs: `docs-fresh/contributing/quality-gates.md`.

### References

- mypy strict: https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-strict
- pyright strict: https://microsoft.github.io/pyright/#/configuration
- ADR-002 § 2 (zero-warning policy), ADR-002 § 3 (suppression floor).

---

## § 2 — Enforce Zero-Warning Quality Gates

**Originally**: ADR-009 · Date: 2026-05-18

### Decision

Every quality gate — `make pre-commit`, `make ci`, `mypy`, `pyright`, `ruff`, `bandit`, `pip-audit`, `gitleaks`, and any pre-commit hook — must end with **zero errors and zero warnings**. Warnings are not informational; they are findings that must be resolved.

Findings are fixed with **real changes to the code**. Suppressions (`# type: ignore`, `# noqa`, `# pyright: ignore`), `Any` widening, `cast(..., Any)`, and tool-configuration relaxation are not acceptable as means of passing a gate.

Eleven pyright checks are promoted from `warning` to `error` in `pyproject.toml`:

| Check | Why it's an error |
|---|---|
| `reportUnknownVariableType` | An inferred-unknown local hides a missing annotation upstream. |
| `reportUnknownMemberType` | A third-party generic that flows unknowns will infect call sites. |
| `reportUnknownArgumentType` | A call passing an unknown value defeats static analysis at the boundary. |
| `reportUnknownParameterType` | A function whose parameter type is unknown can't be safely refactored. |
| `reportUnknownLambdaType` | A lambda with unknown params can't be checked against a callable signature. |
| `reportPrivateUsage` | Reaching into `_private` symbols couples to unstable API surface. |
| `reportUnusedFunction` | An unused function is dead code; if it's actually used dynamically, name it explicitly. |
| `reportUnusedClass` | Same for classes. |
| `reportUnusedImport` | Dead imports rot; if it's a re-export, list it in `__all__`. |
| `reportArgumentType` | A type mismatch at a call site is always a real bug. |
| `reportAttributeAccessIssue` | Reaching for an attribute the type system doesn't see is always a bug or a missing protocol. |

The policy and the forbidden patterns are codified in the workspace rule [`.cursor/rules/enforce-quality-gates.mdc`](https://github.com/mohamed-rekiba/arvel/blob/main/.cursor/rules/enforce-quality-gates.mdc) (`alwaysApply: true`).

### Context

[ADR-002 § 1](ADR-002-quality-and-testing.md) established that `mypy --strict` and `pyright --strict` must both pass. That rule was about which checkers run. It did not say what to do when pyright reports a `warning` instead of an `error`.

In practice, pyright warnings were treated as "advisory" and accumulated. By the close of the framework had 57 outstanding pyright warnings — mostly `reportUnknownMemberType` cascades from SQLAlchemy generics that the team hadn't annotated locally, plus a handful of `reportUnusedFunction` cases where SQLAlchemy event handlers were referenced only by decoration. Each was a small loss of precision; together they meant the framework was no longer auditable as strictly typed.

The team had also, at various points, reached for the easy fixes: a `# type: ignore[attr-defined]` here, a `cast(..., Any)` there. These didn't break anything, but each one removed a piece of the type system's guarantee.

### Options

**A. Continue treating pyright `warning` as advisory.** Status quo. Cheapest in the short term, but the warning count grows monotonically and the strict-typing claim becomes aspirational rather than enforced.

**B. Triage and selectively promote.** Promote one or two of the most-cited checks (`reportUnknownMemberType`) to `error`, leave the rest at `warning`. Compromise position — addresses the worst class but leaves the framework in a "some warnings still acceptable" state that the next contributor has no way to reason about.

**C. Promote every pyright `warning` to `error`, forbid suppressions as a means of passing, fix the underlying code.** ← chosen. Pays the one-time cost of clearing the backlog (57 warnings, ~6 hours of focused work using `TypeGuard`/`TypeIs`/explicit generic annotations) and then makes "the gate is clean" a verifiable, binary state forever.

### Tradeoffs

- **One-time cost**: ~6 hours to fix the 57 outstanding warnings with real code changes (already paid; see commit `5de9483`).
- **Ongoing cost**: every new warning surfaced by a dependency upgrade or a new pyright release becomes a `make pre-commit` failure on the PR that introduced it. The fix is to address the root cause, which is the desired behaviour anyway.
- **One narrow escape hatch**: `# type: ignore[specific-error-code]` is permitted when (1) the cause is provably an upstream library bug or missing stub, (2) a tracking issue is linked in the comment, (3) the scope is the narrowest possible, and (4) the user explicitly approves. Bare `# type: ignore` remains forbidden.
- **Pre-existing suppressions were grandfathered** under FB-010-001, which has since closed (see [ADR-002 § 3](ADR-002-quality-and-testing.md)): the cleanup pass reduced the floor and the remaining suppressions are categorized as the irreducible dual-checker minimum. New code must still not add unjustified suppressions.

### Consequences

- **Gain**: The strict-typing claim in the README, the docs index, and ADR-002 § 1 is now enforced end-to-end. A contributor can trust that `make pre-commit` clean implies a zero-warning baseline.
- **Gain**: `Any` widening to dodge a type error becomes a code-review red flag with a written rule to point at.
- **Accept**: Some dependency upgrades will surface new warnings that need real fixes before the PR can merge. This is the cost of holding the line.
- **Risk**: A contributor unfamiliar with the policy might attempt to suppress a warning to unblock a PR. Mitigation: the workspace rule fires on every Python file edit; the PR template prompts for the gate output; code review enforces it as a non-negotiable.

### Current implementation

- Promoted pyright checks: `packages/arvel/pyproject.toml` `[tool.pyright]` (the eleven checks above are set to `error`).
- Gates: `make pre-commit`, `make ci`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`.
- Policy rule: `.cursor/rules/enforce-quality-gates.mdc`.
- Docs: `docs-fresh/contributing/quality-gates.md`.

---

## § 3 — Two-Checker Policy and the Irreducible Suppression Floor

**Originally**: ADR-010 · Date: 2026-05-18

### Decision

Running `mypy --strict` **and** `pyright --strict` on the same code (per ADR-002 § 1) creates a small, irreducible set of lines where one checker requires a suppression that the other rejects. The framework accepts that floor as the cost of dual-checker enforcement. Specifically:

1. **Suppression count is not a metric.** The number of `# type: ignore[...]` / `# pyright: ignore[...]` / `# noqa: ...` directives in the tree is not a goal in itself. It is monitored as a leading indicator of code quality, not as a target to drive to zero.
2. **Every suppression must be specific.** Bare `# type: ignore` and bare `# noqa` are forbidden ([ADR-002 § 2](ADR-002-quality-and-testing.md)). Every suppression must reference at least one error code and (where the cause is non-obvious) carry a one-line explanation.
3. **Real fixes preferred, suppressions accepted in seven named categories**. The categories below have been investigated and confirmed irreducible without a structural change that costs more than the suppression. New suppressions must fall into one of these categories or be approved as a new one.
4. **Tooling stays as configured.** `mypy.warn_unused_ignores = true` and ruff `RUF100` remain on, so every suppression in the tree is genuinely needed by at least one tool right now. Adding pyright's `reportUnnecessaryTypeIgnoreComment` is rejected — it disagrees with mypy on ~22 lines in the current codebase and would force trading one set of errors for another.

### Context

ADR-002 § 1 mandates parity between `mypy --strict` and `pyright --strict`. ADR-002 § 2 mandates zero errors and zero warnings from every gate. Combined, the two policies forbid letting either checker complain.

A natural follow-up question is: "should suppressions also be zero?" The FB-010-001 deep pass (2026-05-18) answered it empirically:

- **Baseline**: 248 suppression-bearing lines across `packages/`.
- **After seven phases plus a second pass triggered by this ADR**: 143 lines (-105, -42.3 %).
- **Time spent**: ~7-8 focused hours of cross-file refactoring (TypeGuards, Protocols, `cast("T", ...)` for provably-correct narrowing, typed `default_factory`s, helper functions that satisfy both checkers, `isinstance` narrowing in tests, `type(name, bases, ns)` for "definition-is-the-test" classes, `cls: type = X; cls()` for abstract-instantiation tests, named module-level handlers in place of decorator-inner closures).
- **Remaining 143**: categorized below; none is a "dead" suppression. Composition: 61 ruff `# noqa: <code>` + 85 `# type: ignore[code]` / `# pyright: ignore[code]` directives across 143 lines (some lines carry both).

The deep pass demonstrated that the two checkers structurally disagree on Pydantic / SQLAlchemy / FastAPI patterns in ways that no amount of inline gymnastics can reconcile. Examples that came up repeatedly:

- Mypy narrows `ann: object` to `type[FormRequest[Any]]` after an `isinstance` chain; pyright sees it as `Unknown`. Either we suppress for pyright or we wrap in a `TypeGuard` helper that fires on every call.
- Pyright treats `dict.get(key, default)` as returning `T | None` in some contexts where mypy infers `T`. Either we suppress `no-any-return` for mypy or we `cast("T", ...)` and document why.
- Ruff's `TID252` forbids `from ..helpers import …` in tests; pytest's rootdir mechanism finds `from test_notifications.helpers import …` at runtime but mypy and pyright don't. We pick the suppression.

The pass also showed which patterns *are* tractable. The seven phases of FB-010-001 are now exemplars for how to remove suppressions, not how to leave them.

### The seven categories of accepted suppressions

These are the patterns that survived the deep pass. Each is the least-bad option after a fix attempt was tried and rejected.

#### 1. Structural mypy ↔ pyright disagreement (~22 lines)

The two checkers infer different types for the same expression after the same narrowing chain. Removing the suppression breaks one tool; keeping it satisfies both.

- **Form**: `# type: ignore[no-any-return]`, `# pyright: ignore[reportUnknownVariableType]`, `# type: ignore[redundant-cast]`.
- **Why irreducible**: A `TypeGuard` helper that reconciles them adds runtime cost and indirection at every call site. The local suppression is cheaper and clearer.
- **Required comment**: short note pointing at the disagreement, e.g. `# type: ignore[no-any-return]  # mypy narrows, pyright doesn't`.

#### 2. Decorator-registered handlers in production code (~0 lines today; pattern documented)

`@app.get("/foo")` / `@event.listens_for(...)` register `def handler(): ...` with a framework, but neither checker can see the registration so they flag the handler as unused. Phase 2 of FB-010-001 cleared 33 occurrences in HTTP tests with two patterns:

- **For tests**: `assert any(r.handler is fn for r in Router.singleton().routes())` strengthens the assertion AND references the handler by name. Or `del handler` after the decorator when the test doesn't need to inspect the route.
- **For production code**: extract the handler to a module-level named function, then call `event.listen(target, name, handler, ...)` explicitly instead of `@event.listens_for(...)`. Pyright then sees the function via the explicit call site. Applied to `arvel/database/model.py:Timestamps` and `arvel/database/events.py:bind_observer` (see `_wire_sync_event` helper).
- **For Typer single-command callbacks**: `del _main` after the `@app.callback()` decorator (only the registration reference matters at runtime).

This category is empty today. Listed because the patterns are the standing answer for new decorator-registered code.

#### 3. White-box test access to underscore-prefixed internals (~21 lines)

Tests inspect `app._booted`, `app._provider_classes`, `builder._routing_paths`, `Router.singleton()._add`, SQLA's `row._mapping`, container's `_singletons` / `_instances` / `_bindings`, etc. to assert internal state changed.

- **Form**: `# pyright: ignore[reportPrivateUsage]` (sometimes paired with `# noqa: SLF001`).
- **Why irreducible**: exposing the internals as public API just to satisfy a type check inverts the visibility relationship. The suppression is correct; the internal access is intentional.
- **Permitted**: on test files; in production code only when calling a sibling-module-private API where the caller is the *authorized* caller (e.g., `Route` → `Router._add`, documented in a one-line comment).

#### 4. Runtime defences for invalid input that bypasses typing (~3 lines)

`if not isinstance(x, str): raise TypeError(...)` after a typed parameter `x: str`. Pyright correctly marks the branch unreachable, but we want the runtime check anyway because callers can hand us anything at runtime.

- **Form**: `# type: ignore[unreachable]` and `# pyright: ignore[reportUnnecessaryIsInstance]`.
- **Why irreducible**: removing the check removes a real defence. Removing the suppression hides a real one. The suppression *is* the right answer.
- **Locations** (snapshot): `container/container.py` (×2), plus CLI input
  validation (now under `arvel/console/`, the `arvel-cli` package no longer exists).

#### 5. `Container.make(SomeProtocol)` and abstract-class instantiation in tests (~4 lines)

Two adjacent patterns where a checker flags as impossible what a test verifies at runtime:

- `Container.make(SomeProtocol)` — container resolves Protocols and ABCs perfectly at runtime; mypy flags the call as `type-abstract`. The planned fix is overloads on `Container.make`; comments at `container/container.py:33,114` track the work. Suppressing in 2 test files is cheaper than shipping the overloads before they're needed.
- "Abstract class instantiation rejected at runtime" tests — `Mailable()`, `Notification()`, `Listener()`, etc. inside `pytest.raises(TypeError)`. Phase-2-style fix applied: bind to a `cls: type = SomeAbstract` first, then call `cls()`. The `: type` annotation strips the abstract metadata and both checkers accept the call. This pattern cleared 5 occurrences; the remaining 2 in `tests/http/test_provider.py` and `tests/qa_post/test_edge_cases.py` are the Container.make() type-abstract case above.
- **Form**: `# type: ignore[type-abstract]`.

#### 6. Pytest path mechanics for shared test helpers (~3 lines)

`from test_notifications.helpers import …` works at runtime because pytest adds `tests/` to `sys.path`. Mypy and pyright don't replicate that resolution.

- **Form**: `# type: ignore[import-not-found]`.
- **Why irreducible**: ruff `TID252` forbids the relative-import workaround (`from ..helpers import …`). Reconfiguring mypy / pyright to add `tests/` to their search paths breaks the rest of the import graph.
- **Locations** (current): `tests/test_notifications/channels/*.py`.

#### 7. Test fixtures whose definition *is* the test (~0 lines today; pattern documented)

`class BadMigration(Migration): ...` exists only to be passed to `pytest.raises(MigrationNotReversibleError)` — the `__init_subclass__` raises at class-definition time. Pyright flags the class as unused even with an underscore prefix.

- **Standing fix**: use `type(name, bases, namespace)` to create the class dynamically inside the `with pytest.raises(...)` block. Pyright sees the call to `type(...)`, not an unused class statement. Both `tests/database/test_migrations.py` (×3) and `tests/database/test_migrations_more.py` (×1) now use this pattern. Category is empty today.
- **Form when needed**: `# pyright: ignore[reportUnusedClass]`.

#### Additional accepted patterns (smaller counts)

- **Project-specific ruff exemptions** (61 `# noqa: <code>`) — `S102` (intentional dynamic `exec()` in tests), `S307` (intentional `eval`), `S307` / `S307` (subprocess with audited args), `E402` (re-exports after `pytest.importorskip`), `BLE001` (blind `except` in middleware / facade boundaries), `PLR0913` (legitimately long signatures in builder APIs), `SLF001` (sibling-module-private API call), `N818` (exception names that don't end in `Error` for stdlib-compatibility classes), `S105` (test passwords), `DTZ005` (UTC-naive in a single, justified place), `E712` (intentional `== True` in QB tests). Every `# noqa` carries the specific code; bare `# noqa` is forbidden.
- **Intentional monkey-patching in tests** (3 `# type: ignore[method-assign]`) — `tests/container/test_extending.py` patches `Greeter.greet` to verify the `extend` API does what it claims. Rewriting as a subclass changes test semantics.
- **`sys.modules[name] = None` to simulate missing optional deps** (3 `# type: ignore[assignment]`) — the documented technique for forcing `ImportError` in tests. The typed signature of `sys.modules` rejects `None`; the runtime behaviour we want is exactly that. Used in `tests/test_optional_deps.py` and `tests/storage/test_s3_driver.py`.
- **`fakeredis` without type stubs** (2 `# type: ignore[import-untyped]`) — third-party test dep with no stubs published; we can't ship type information for a library we don't own.
- **Pydantic overload resolution with parametrized `default: object`** (2 `# type: ignore[call-overload]`) — `env(key, default)` has three `@overload`s that can't pick a single arm when `default: object` (the parametrize union type). Skipping per-test overload narrowing would defeat the parametrize.
- **SQLAlchemy `result.rowcount` cross-driver** (1 `# type: ignore[attr-defined]`) — typed as `int | None` only on some `Result` subclasses depending on driver; the production path needs the runtime read regardless.

### Options considered

**A. Set a hard suppression budget (e.g., ≤150) and gate the PR on it.** Numeric budgets create cliff effects: a refactor that legitimately needs +1 fails CI even though the change is healthier than what it replaces. Rejected.

**B. Drive to zero suppressions.** Possible only by removing one of the checkers (violates ADR-002 § 1) or by relaxing strictness (violates ADR-002 § 2) or by widening to `Any` everywhere ([forbidden by `.cursor/rules/enforce-quality-gates.mdc`](https://github.com/mohamed-rekiba/arvel/blob/main/.cursor/rules/enforce-quality-gates.mdc)). Rejected.

**C. Enable pyright `reportUnnecessaryTypeIgnoreComment`.** Pyright flagged 26 lines as "dead" during the FB-010-001 deep pass; investigation showed 24 of those are needed by mypy. Enabling the check would force mypy errors back into the gate. Rejected.

**D. Document the categories, require justifications, monitor (chosen).** Lists what is and isn't acceptable. Lets PRs proceed when the suppression fits a known category, forces a discussion when it doesn't. Doesn't penalize healthy refactors that swap one suppression for another.

### Tradeoffs

- **Loss**: there is no single number a contributor can point at to say "the codebase is fully typed." The honest answer is "fully type-checked under both strict checkers, with 164 documented suppressions in seven categories."
- **Gain**: contributors stop trying to clear the suppression count as an end in itself. The energy goes into real fixes, which is what the seven phases of FB-010-001 actually delivered.
- **Gain**: code review has a written rule to point at when a contributor reaches for a suppression. If it doesn't match one of the seven categories, the conversation is "let's find the real fix" rather than "this is too hard."
- **Risk**: the category list goes stale as tools evolve. Mitigation: revisit on every mypy / pyright major-version bump; if a category empties, drop it; if a new pattern emerges that's irreducible, add it via an ADR amendment.

### Consequences

- **FB-010-001 closes**. The 143 remaining suppression-bearing lines are the floor under the current toolchain. No further "cleanup pass" is scheduled; specific reductions happen opportunistically inside feature work when a refactor makes them tractable.
- **The `.cursor/rules/enforce-quality-gates.mdc` rule** stays as-is. The narrow escape hatch defined there (specific error code + tracking comment + user approval) is the mechanism for adding new suppressions; this ADR is the policy that defines what "acceptable" means.
- **Standing patterns** documented in this ADR (`type(name, bases, ns)` for definition-is-the-test, `cls: type = X` for abstract-instantiation tests, named module-level handlers in place of decorator-inner closures, `isinstance` narrowing instead of `union-attr` suppression) are the reference answers for new code.

### References

- [ADR-002 § 1 — Enforce both `mypy --strict` and `pyright --strict`](ADR-002-quality-and-testing.md)
- [ADR-002 § 2 — Enforce zero-warning quality gates](ADR-002-quality-and-testing.md)
- [`.cursor/rules/enforce-quality-gates.mdc`](https://github.com/mohamed-rekiba/arvel/blob/main/.cursor/rules/enforce-quality-gates.mdc)
- FB-010-001 commit chain: `8795c86` (phase 1) → `d1425ab` (phase 7) plus the ADR-002 § 3 second pass (248 → 143 suppression-bearing lines, -42.3 %)

---

## § 4 — Per-module coverage gates (promoted from FB-010)

**Originally**: ADR-011 · Date: 2026-05-17

### Context

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

### Decision

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

### Consequences

**Positive**:
- Impossible for a new low-coverage module to slip in under cover of
  high-coverage siblings.
- Per-module section appears as part of the standard `pytest --cov` run, so
  CI logs are self-explanatory:

  ```
  ================= Per-module coverage gates (FB-010 / ADR-002 § 4) =================
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

### Current implementation

- Floors: root `pyproject.toml` `[tool.coverage.arvel_per_module]` (still the
  nine modules and values quoted above).
- Enforcement: workspace-root `conftest.py` (`pytest_terminal_summary` +
  `pytest_sessionfinish`).
- Docs: `docs-fresh/contributing/quality-gates.md`.

---

## § 5 — create_test_app() as async context manager

**Originally**: ADR-012 · Date: 2026-05-23

### Context

The demo uses a `StarterApp` class (wrapping `Application` + `FastAPI`) with manual
`create_app()` + `await app.shutdown()` in test fixtures. Two alternatives were considered:
- Keep the class-based approach with explicit `async with`-like lifecycle
- Use an `AsyncContextManager` via `@asynccontextmanager`

### Decision

`create_test_app()` is an `@asynccontextmanager` that yields an `httpx.AsyncClient`.

### Rationale

The context manager pattern is cleaner for test fixtures: `async with create_test_app(...)
as client:` eliminates the explicit shutdown call and makes it impossible to forget teardown.
The `httpx.AsyncClient` as the yielded value means tests directly interact with the client
without accessing the wrapper object.

ASGI types use `starlette.types.Scope`, `Receive`, `Send` (not `Any`) to satisfy `mypy
--strict` without suppressions.

### Consequences

- The demo's `StarterApp` class and `create_app()` are removed in favor of the context manager
- Tests use the `async with create_test_app(...) as client:` idiom
- `create_test_app` is exported from `arvel.testing` (not `arvel` root — production-code guard)

### Current implementation

- Code: `packages/arvel/src/arvel/testing/app.py` (yields `httpx.AsyncClient`, boots on entry, shuts down on exit via `finally`; the bootable app is a `Protocol`).
- Docs: `docs-fresh/contributing/testing.md`.

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-008 | 2026-05-17 | Enforce both `mypy --strict` and `pyright --strict` (parity required) | § 1 |
| ADR-009 | 2026-05-18 | Enforce Zero-Warning Quality Gates | § 2 |
| ADR-010 | 2026-05-18 | Two-Checker Policy and the Irreducible Suppression Floor | § 3 |
| ADR-011 | 2026-05-17 | Per-module coverage gates (promoted from FB-010) | § 4 |
| ADR-012 | 2026-05-23 | create_test_app() as async context manager | § 5 |
