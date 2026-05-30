# ADR-051: Enforce Zero-Warning Quality Gates

**Status**: Accepted
**Date**: 2026-05-18

## Decision

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

## Context

[ADR-005](ADR-005-mypy-pyright-parity.md) established that `mypy --strict` and `pyright --strict` must both pass. That rule was about which checkers run. It did not say what to do when pyright reports a `warning` instead of an `error`.

In practice, pyright warnings were treated as "advisory" and accumulated. By the close of the framework had 57 outstanding pyright warnings — mostly `reportUnknownMemberType` cascades from SQLAlchemy generics that the team hadn't annotated locally, plus a handful of `reportUnusedFunction` cases where SQLAlchemy event handlers were referenced only by decoration. Each was a small loss of precision; together they meant the framework was no longer auditable as strictly typed.

The team had also, at various points, reached for the easy fixes: a `# type: ignore[attr-defined]` here, a `cast(..., Any)` there. These didn't break anything, but each one removed a piece of the type system's guarantee.

## Options

**A. Continue treating pyright `warning` as advisory.** Status quo. Cheapest in the short term, but the warning count grows monotonically and the strict-typing claim becomes aspirational rather than enforced.

**B. Triage and selectively promote.** Promote one or two of the most-cited checks (`reportUnknownMemberType`) to `error`, leave the rest at `warning`. Compromise position — addresses the worst class but leaves the framework in a "some warnings still acceptable" state that the next contributor has no way to reason about.

**C. Promote every pyright `warning` to `error`, forbid suppressions as a means of passing, fix the underlying code.** ← chosen. Pays the one-time cost of clearing the backlog (57 warnings, ~6 hours of focused work using `TypeGuard`/`TypeIs`/explicit generic annotations) and then makes "the gate is clean" a verifiable, binary state forever.

## Tradeoffs

- **One-time cost**: ~6 hours to fix the 57 outstanding warnings with real code changes (already paid; see commit `5de9483`).
- **Ongoing cost**: every new warning surfaced by a dependency upgrade or a new pyright release becomes a `make pre-commit` failure on the PR that introduced it. The fix is to address the root cause, which is the desired behaviour anyway.
- **One narrow escape hatch**: `# type: ignore[specific-error-code]` is permitted when (1) the cause is provably an upstream library bug or missing stub, (2) a tracking issue is linked in the comment, (3) the scope is the narrowest possible, and (4) the user explicitly approves. Bare `# type: ignore` remains forbidden.
- **Pre-existing suppressions are grandfathered**: there are ~200 historical `# type: ignore` / `# noqa` / `# pyright: ignore` directives across the codebase from before this policy. They are tracked as FB-010-001 for a dedicated cleanup pass; new code must not add to the count.

## Consequences

- **Gain**: The strict-typing claim in the README, the docs index, and ADR-005 is now enforced end-to-end. A contributor can trust that `make pre-commit` clean implies a zero-warning baseline.
- **Gain**: `Any` widening to dodge a type error becomes a code-review red flag with a written rule to point at.
- **Accept**: Some dependency upgrades will surface new warnings that need real fixes before the PR can merge. This is the cost of holding the line.
- **Risk**: A contributor unfamiliar with the policy might attempt to suppress a warning to unblock a PR. Mitigation: the workspace rule fires on every Python file edit; the PR template prompts for the gate output; code review enforces it as a non-negotiable.
