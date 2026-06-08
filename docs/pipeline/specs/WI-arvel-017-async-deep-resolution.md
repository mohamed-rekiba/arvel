# WI-arvel-017 — `amake` must resolve async bindings at any depth

- **Module**: 17 — service container (DI)
- **Complexity**: L2
- **Risk tier**: 2
- **Data classification**: internal
- **Status**: completed

## Problem

`Container._aresolve` delegated auto-wiring and concrete-class bindings to the
**sync** `_instantiate`, which resolves every constructor dependency with
`allow_async=False`.

- **C1 (Critical)** — `amake(Service)` raised `BindingResolutionError`
  (wrapping `AsyncBindingError`) the moment any transitive dependency was bound to
  an `async def` factory. So `amake` — whose entire purpose is async resolution —
  only worked when the async binding was the root of the graph. Reproduced with
  `Service -> Repo -> Db` where `Db` is async-bound.
- **C2 (coupled, latent)** — the async path had no cycle guard (`_resolve` has
  `if abstract in path: raise CircularDependencyError`; `_aresolve` did not), so a
  cyclic async graph recursed to `RecursionError` instead of raising the typed
  error.

## Fix

In `container.py`:

- Added `_ainstantiate`, the async twin of `_instantiate`: each typed constructor
  parameter is resolved with `await self._aresolve(...)`, threading `path`.
- `_aresolve` now strips generic-alias origins and guards `if abstract in path:
  raise CircularDependencyError` (parity with `_resolve`), and routes the auto-wire
  fallback, the concrete-class binding branch, and the contextual concrete-class
  branch through `_ainstantiate`.
- Sync `make`, async-factory bindings (still invoked with no args), scope/singleton
  caching, and contextual factories are unchanged.

## Acceptance criteria

- `amake(Service)` resolves a graph where a transitive dependency is async-bound.
- `amake` resolves an async dependency through an explicitly bound concrete class.
- A contextual concrete-class binding with an async dependency resolves via `amake`.
- `amake` raises `CircularDependencyError` (not `RecursionError`) on a cycle.
- Sync `make` still raises on an async binding anywhere in the graph (no regression).
- mypy --strict, pyright, ruff check, ruff format clean; full arvel suite green.

## Out of scope (deferred)

- `AsyncSession` bound `TRANSIENT` vs the provider docstring's "scoped" — the real
  per-request unit-of-work is the `DatabaseTransaction` contextvar session, so the
  binding scope is a design call, not a clean bug.
- `alias()` names are never read by `make()` (inert string aliases).
- `extend()` invalidates `_singletons` but not `_instances`.

## Files

- `packages/arvel/src/arvel/container/container.py`
- `packages/arvel/tests/container/test_wi_017_async_deep_resolution.py` (new)
- `docs/site/docs/core-concepts/service-container.md`
