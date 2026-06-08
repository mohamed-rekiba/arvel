# Epic: Container amake must resolve async bindings at any depth

## Summary
The container's async resolver (`amake`/`acall`) delegated auto-wiring and
concrete-class bindings to the sync `_instantiate`, which resolves constructor
dependencies with `allow_async=False`. So `amake` raised the moment a *transitive*
dependency was bound to an `async def` factory — it only worked when the async
binding sat at the root of the graph, defeating the point of having an async
resolver. The async path also lacked the cycle guard the sync path has, so a cyclic
async graph hit `RecursionError` instead of `CircularDependencyError`. Added an
async instantiate that threads `_aresolve` (and `path`) through constructor deps.

**Module:** container / DI · **Spec:** `docs/pipeline/specs/WI-arvel-017-async-deep-resolution.md`

## Stories

### Story 1: Async dependencies resolve through the whole graph
**As a** developer building services on the async path, **I want** `amake` to
auto-wire a class whose dependency (direct or transitive) is async-bound, **so that**
I can compose services without flattening every async binding to the root.

**Acceptance Criteria**:
- [x] Given `Service -> Repo -> Db` with `Db` async-bound, when `amake(Service)`, then it resolves and `Db` is built.
- [x] Given a concrete class bound with `bind(Repo)` and an async-bound `Db`, when `amake(Repo)`, then it resolves.
- [x] Given a contextual concrete-class binding with an async dependency, when `amake`, then it resolves.
- [x] Given a synchronous `make` on any binding that reaches an async factory, then it still raises (no regression).

### Story 2: Cycles fail with a typed error on the async path
**As a** developer, **I want** a circular async graph to raise
`CircularDependencyError`, **so that** I get a clear error instead of a
`RecursionError` stack overflow.

**Acceptance Criteria**:
- [x] Given a cyclic dependency, when `amake`, then `CircularDependencyError` is raised.

**Security Requirements**:
- [x] No behavior change to sync resolution, scope/singleton caching, or async-factory invocation.

**Documentation Requirements**:
- [x] `docs/site/docs/core-concepts/service-container.md` states `amake` resolves async bindings at any depth and sync `make` still rejects them.

**Requirement Refs**: SPEC-1, SPEC-2, SPEC-3, SPEC-4, SPEC-5
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001..016.

## Notes
- Folded-in: added the missing generic-alias origin strip + cycle guard to the async
  path (parity with the sync `_resolve`).
- Deferred follow-ups (separate work items):
  - **`AsyncSession` TRANSIENT vs "scoped" docstring** — real per-request session is
    the `DatabaseTransaction` contextvar session; binding scope is a design call.
  - **`alias()`** stores names `make()` never reads (inert string aliases).
  - **`extend()`** invalidates `_singletons` but not `_instances`.
