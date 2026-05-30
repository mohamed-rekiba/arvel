# ADR-052: Two-Checker Policy and the Irreducible Suppression Floor

**Status**: Accepted
**Date**: 2026-05-18
**Supersedes**: nothing; complements [ADR-005](ADR-005-mypy-pyright-parity.md) and [ADR-051](ADR-051-enforce-quality-gates.md).

## Decision

Running `mypy --strict` **and** `pyright --strict` on the same code (per ADR-005) creates a small, irreducible set of lines where one checker requires a suppression that the other rejects. The framework accepts that floor as the cost of dual-checker enforcement. Specifically:

1. **Suppression count is not a metric.** The number of `# type: ignore[...]` / `# pyright: ignore[...]` / `# noqa: ...` directives in the tree is not a goal in itself. It is monitored as a leading indicator of code quality, not as a target to drive to zero.
2. **Every suppression must be specific.** Bare `# type: ignore` and bare `# noqa` are forbidden ([ADR-051](ADR-051-enforce-quality-gates.md)). Every suppression must reference at least one error code and (where the cause is non-obvious) carry a one-line explanation.
3. **Real fixes preferred, suppressions accepted in seven named categories**. The categories below have been investigated and confirmed irreducible without a structural change that costs more than the suppression. New suppressions must fall into one of these categories or be approved as a new one.
4. **Tooling stays as configured.** `mypy.warn_unused_ignores = true` and ruff `RUF100` remain on, so every suppression in the tree is genuinely needed by at least one tool right now. Adding pyright's `reportUnnecessaryTypeIgnoreComment` is rejected — it disagrees with mypy on ~22 lines in the current codebase and would force trading one set of errors for another.

## Context

ADR-005 mandates parity between `mypy --strict` and `pyright --strict`. ADR-051 mandates zero errors and zero warnings from every gate. Combined, the two policies forbid letting either checker complain.

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

## The seven categories of accepted suppressions

These are the patterns that survived the deep pass. Each is the least-bad option after a fix attempt was tried and rejected.

### 1. Structural mypy ↔ pyright disagreement (~22 lines)

The two checkers infer different types for the same expression after the same narrowing chain. Removing the suppression breaks one tool; keeping it satisfies both.

- **Form**: `# type: ignore[no-any-return]`, `# pyright: ignore[reportUnknownVariableType]`, `# type: ignore[redundant-cast]`.
- **Why irreducible**: A `TypeGuard` helper that reconciles them adds runtime cost and indirection at every call site. The local suppression is cheaper and clearer.
- **Required comment**: short note pointing at the disagreement, e.g. `# type: ignore[no-any-return]  # mypy narrows, pyright doesn't`.

### 2. Decorator-registered handlers in production code (~0 lines today; pattern documented)

`@app.get("/foo")` / `@event.listens_for(...)` register `def handler(): ...` with a framework, but neither checker can see the registration so they flag the handler as unused. Phase 2 of FB-010-001 cleared 33 occurrences in HTTP tests with two patterns:

- **For tests**: `assert any(r.handler is fn for r in Router.singleton().routes())` strengthens the assertion AND references the handler by name. Or `del handler` after the decorator when the test doesn't need to inspect the route.
- **For production code**: extract the handler to a module-level named function, then call `event.listen(target, name, handler, ...)` explicitly instead of `@event.listens_for(...)`. Pyright then sees the function via the explicit call site. Applied to `arvel/database/model.py:Timestamps` and `arvel/database/events.py:bind_observer` (see `_wire_sync_event` helper).
- **For Typer single-command callbacks**: `del _main` after the `@app.callback()` decorator (only the registration reference matters at runtime).

This category is empty today. Listed because the patterns are the standing answer for new decorator-registered code.

### 3. White-box test access to underscore-prefixed internals (~21 lines)

Tests inspect `app._booted`, `app._provider_classes`, `builder._routing_paths`, `Router.singleton()._add`, SQLA's `row._mapping`, container's `_singletons` / `_instances` / `_bindings`, etc. to assert internal state changed.

- **Form**: `# pyright: ignore[reportPrivateUsage]` (sometimes paired with `# noqa: SLF001`).
- **Why irreducible**: exposing the internals as public API just to satisfy a type check inverts the visibility relationship. The suppression is correct; the internal access is intentional.
- **Permitted**: on test files; in production code only when calling a sibling-module-private API where the caller is the *authorized* caller (e.g., `Route` → `Router._add`, documented in a one-line comment).

### 4. Runtime defences for invalid input that bypasses typing (~3 lines)

`if not isinstance(x, str): raise TypeError(...)` after a typed parameter `x: str`. Pyright correctly marks the branch unreachable, but we want the runtime check anyway because callers can hand us anything at runtime.

- **Form**: `# type: ignore[unreachable]` and `# pyright: ignore[reportUnnecessaryIsInstance]`.
- **Why irreducible**: removing the check removes a real defence. Removing the suppression hides a real one. The suppression *is* the right answer.
- **Locations** (current): `container/container.py` (×2), `arvel-cli/_validation.py` (×1).

### 5. `Container.make(SomeProtocol)` and abstract-class instantiation in tests (~4 lines)

Two adjacent patterns where a checker flags as impossible what a test verifies at runtime:

- `Container.make(SomeProtocol)` — container resolves Protocols and ABCs perfectly at runtime; mypy flags the call as `type-abstract`. The planned fix is overloads on `Container.make`; comments at `container/container.py:33,114` track the work. Suppressing in 2 test files is cheaper than shipping the overloads before they're needed.
- "Abstract class instantiation rejected at runtime" tests — `Mailable()`, `Notification()`, `Listener()`, etc. inside `pytest.raises(TypeError)`. Phase-2-style fix applied: bind to a `cls: type = SomeAbstract` first, then call `cls()`. The `: type` annotation strips the abstract metadata and both checkers accept the call. This pattern cleared 5 occurrences; the remaining 2 in `tests/http/test_provider.py` and `tests/qa_post/test_edge_cases.py` are the Container.make() type-abstract case above.
- **Form**: `# type: ignore[type-abstract]`.

### 6. Pytest path mechanics for shared test helpers (~3 lines)

`from test_notifications.helpers import …` works at runtime because pytest adds `tests/` to `sys.path`. Mypy and pyright don't replicate that resolution.

- **Form**: `# type: ignore[import-not-found]`.
- **Why irreducible**: ruff `TID252` forbids the relative-import workaround (`from ..helpers import …`). Reconfiguring mypy / pyright to add `tests/` to their search paths breaks the rest of the import graph.
- **Locations** (current): `tests/test_notifications/channels/*.py`.

### 7. Test fixtures whose definition *is* the test (~0 lines today; pattern documented)

`class BadMigration(Migration): ...` exists only to be passed to `pytest.raises(MigrationNotReversibleError)` — the `__init_subclass__` raises at class-definition time. Pyright flags the class as unused even with an underscore prefix.

- **Standing fix**: use `type(name, bases, namespace)` to create the class dynamically inside the `with pytest.raises(...)` block. Pyright sees the call to `type(...)`, not an unused class statement. Both `tests/database/test_migrations.py` (×3) and `tests/database/test_migrations_more.py` (×1) now use this pattern. Category is empty today.
- **Form when needed**: `# pyright: ignore[reportUnusedClass]`.

### Additional accepted patterns (smaller counts)

- **Project-specific ruff exemptions** (61 `# noqa: <code>`) — `S102` (intentional dynamic `exec()` in tests), `S307` (intentional `eval`), `S307` / `S307` (subprocess with audited args), `E402` (re-exports after `pytest.importorskip`), `BLE001` (blind `except` in middleware / facade boundaries), `PLR0913` (legitimately long signatures in builder APIs), `SLF001` (sibling-module-private API call), `N818` (exception names that don't end in `Error` for stdlib-compatibility classes), `S105` (test passwords), `DTZ005` (UTC-naive in a single, justified place), `E712` (intentional `== True` in QB tests). Every `# noqa` carries the specific code; bare `# noqa` is forbidden.
- **Intentional monkey-patching in tests** (3 `# type: ignore[method-assign]`) — `tests/container/test_extending.py` patches `Greeter.greet` to verify the `extend` API does what it claims. Rewriting as a subclass changes test semantics.
- **`sys.modules[name] = None` to simulate missing optional deps** (3 `# type: ignore[assignment]`) — the documented technique for forcing `ImportError` in tests. The typed signature of `sys.modules` rejects `None`; the runtime behaviour we want is exactly that. Used in `tests/test_optional_deps.py` and `tests/storage/test_s3_driver.py`.
- **`fakeredis` without type stubs** (2 `# type: ignore[import-untyped]`) — third-party test dep with no stubs published; we can't ship type information for a library we don't own.
- **Pydantic overload resolution with parametrized `default: object`** (2 `# type: ignore[call-overload]`) — `env(key, default)` has three `@overload`s that can't pick a single arm when `default: object` (the parametrize union type). Skipping per-test overload narrowing would defeat the parametrize.
- **SQLAlchemy `result.rowcount` cross-driver** (1 `# type: ignore[attr-defined]`) — typed as `int | None` only on some `Result` subclasses depending on driver; the production path needs the runtime read regardless.

## Options considered

**A. Set a hard suppression budget (e.g., ≤150) and gate the PR on it.** Numeric budgets create cliff effects: a refactor that legitimately needs +1 fails CI even though the change is healthier than what it replaces. Rejected.

**B. Drive to zero suppressions.** Possible only by removing one of the checkers (violates ADR-005) or by relaxing strictness (violates ADR-051) or by widening to `Any` everywhere ([forbidden by `.cursor/rules/enforce-quality-gates.mdc`](https://github.com/mohamed-rekiba/arvel/blob/main/.cursor/rules/enforce-quality-gates.mdc)). Rejected.

**C. Enable pyright `reportUnnecessaryTypeIgnoreComment`.** Pyright flagged 26 lines as "dead" during the FB-010-001 deep pass; investigation showed 24 of those are needed by mypy. Enabling the check would force mypy errors back into the gate. Rejected.

**D. Document the categories, require justifications, monitor (chosen).** Lists what is and isn't acceptable. Lets PRs proceed when the suppression fits a known category, forces a discussion when it doesn't. Doesn't penalize healthy refactors that swap one suppression for another.

## Tradeoffs

- **Loss**: there is no single number a contributor can point at to say "the codebase is fully typed." The honest answer is "fully type-checked under both strict checkers, with 164 documented suppressions in seven categories."
- **Gain**: contributors stop trying to clear the suppression count as an end in itself. The energy goes into real fixes, which is what the seven phases of FB-010-001 actually delivered.
- **Gain**: code review has a written rule to point at when a contributor reaches for a suppression. If it doesn't match one of the seven categories, the conversation is "let's find the real fix" rather than "this is too hard."
- **Risk**: the category list goes stale as tools evolve. Mitigation: revisit on every mypy / pyright major-version bump; if a category empties, drop it; if a new pattern emerges that's irreducible, add it via an ADR amendment.

## Consequences

- **FB-010-001 closes**. The 143 remaining suppression-bearing lines are the floor under the current toolchain. No further "cleanup pass" is scheduled; specific reductions happen opportunistically inside feature work when a refactor makes them tractable.
- **The `.cursor/rules/enforce-quality-gates.mdc` rule** stays as-is. The narrow escape hatch defined there (specific error code + tracking comment + user approval) is the mechanism for adding new suppressions; this ADR is the policy that defines what "acceptable" means.
- **Standing patterns** documented in this ADR (`type(name, bases, ns)` for definition-is-the-test, `cls: type = X` for abstract-instantiation tests, named module-level handlers in place of decorator-inner closures, `isinstance` narrowing instead of `union-attr` suppression) are the reference answers for new code.

## References

- [ADR-005 — Enforce both `mypy --strict` and `pyright --strict`](ADR-005-mypy-pyright-parity.md)
- [ADR-051 — Enforce zero-warning quality gates](ADR-051-enforce-quality-gates.md)
- [`.cursor/rules/enforce-quality-gates.mdc`](https://github.com/mohamed-rekiba/arvel/blob/main/.cursor/rules/enforce-quality-gates.mdc)
- FB-010-001 commit chain: `8795c86` (phase 1) → `d1425ab` (phase 7) plus the ADR-052 second pass (248 → 143 suppression-bearing lines, -42.3 %)
