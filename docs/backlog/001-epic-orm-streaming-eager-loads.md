# Epic: ORM streaming honors eager loads (no silent N+1)

## Summary
Streaming terminals on the ORM query builder must never silently drop a `with_()`
eager-load request. A server-side cursor that cannot batch eager loads fails fast;
the in-memory tree terminal honors eager loads like its non-streaming sibling.

**Module:** database / ORM · **Spec:** `docs/pipeline/specs/WI-arvel-001-stream-eager-loads.md`

## Stories

### Story 1: Fail fast when streaming with eager loads
**As a** developer streaming a large table, **I want** an immediate, explanatory error
if I request eager loads on `stream()`, **so that** I never ship undetected N+1
queries or silently-empty relations.

**Acceptance Criteria**:
- [ ] Given a query with `with_("rel")` (FK-method, pivot, morph, recursive, chaperone, or SA `selectinload`), when I call `stream()`, then `EagerLoadNotStreamableError` is raised.
- [ ] Given that error, when I read its message, then it names the offending relations and points to `lazy()`/`chunk()`/`chunk_by_id()`.
- [ ] Given a `stream()` with no eager loads, when I iterate it, then all rows are yielded in order with no error.

**Security Requirements**:
- [ ] None (internal data-access contract).

**Documentation Requirements**:
- [ ] `docs/orm/query-builder.md` documents the streaming terminals and the eager-load constraint.

**Requirement Refs**: SPEC-1, SPEC-2, SPEC-3
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: Tree assembly honors eager loads
**As a** developer building a category tree, **I want** `as_tree()` to honor `with_()`
the same way `all()` does, **so that** rendering the tree doesn't trigger per-node
queries.

**Acceptance Criteria**:
- [ ] Given `Model.recursive(parent_key=…).with_("rel")`, when I call `as_tree()`, then `rel` is eager-loaded onto every node (served from cache, no extra queries).
- [ ] Given the same query, when I compare to `all()`, then both leave identical eager-cache state.

**Documentation Requirements**:
- [ ] `docs/orm/query-builder.md` notes `as_tree()` honors eager loads.

**Requirement Refs**: SPEC-4
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 3: Type-safe, regression-free public surface
**As a** maintainer, **I want** the new error in the public API with full type safety,
**so that** callers can catch it and the strict type gate stays green.

**Acceptance Criteria**:
- [ ] Given the public package, when I import `EagerLoadNotStreamableError` from `arvel.database`, then it resolves.
- [ ] Given the type gate, when I run mypy --strict and pyright, then there are zero errors and no new `# type: ignore`/`cast`/`Any` at public boundaries.
- [ ] Given the ORM suite, when I run it, then all existing tests still pass.

**Requirement Refs**: SPEC-5, SPEC-6, SPEC-7
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- None (foundational ORM module).

## Notes
- Deferred follow-ups (separate backlog items, part of the broader recursive-eager
  parity gap — research F5):
  - `_Recursive` (`node.descendants()`) builders honoring arbitrary `with_()`.
  - `Model.with_("rel").recursive(...)` should carry pending eager specs into the
    `RecursiveQueryBuilder` (today only `Model.recursive(...).with_("rel")` works;
    the reversed order silently drops the eager load). Note: this also requires the
    recursive terminals to apply SA `selectinload`, which they currently don't —
    hence it's a coordinated change, not a one-line copy.
  - `hasManyThrough`/`hasOneThrough` `with_()` eager integration.
  - `$with` default eager loads; `preventLazyLoading` strict mode.
