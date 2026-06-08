# Epic: Context dehydrate/hydrate round-trips hidden data

## Summary
`Context.dehydrate()`/`hydrate()` must capture and restore **both** the visible
and hidden stores, matching Laravel — hidden context is hidden from logs and
`all()`/`get()`, not from the queue.

**Module:** context · **Spec:** `docs/pipeline/specs/WI-arvel-022-context-dehydrate-hidden.md`

## Stories

### Story 1: hidden context survives the queue round-trip
**As a** developer sharing context with a queued job, **I want** hidden context to
dehydrate and hydrate alongside visible context, **so that** values added in a
`dehydrating` hook (e.g. locale) are available as hidden data in the worker —
exactly like Laravel.

**Acceptance Criteria**:
- [x] `dehydrate()` returns `{"data": {...}, "hidden": {...}}`.
- [x] After `hydrate(payload)`, hidden keys are readable via `get_hidden` but not in `all()`.
- [x] `hydrate()` replaces existing state (no stale merge).
- [x] A taken `dehydrate()` snapshot is decoupled from later live-store mutations.

**Security Requirements**:
- [x] Hidden context still excluded from `all()`/`get()` and from log surfaces.

**Documentation Requirements**:
- [x] Repository docstring corrected — "hidden from logs, not from the queue."

**Requirement Refs**: SPEC-1 · **Priority**: Must · **Complexity**: Small · **Status**: Done

## Out of scope (deferred)
- Auto-dehydrate-on-dispatch queue wiring; `pull`/`pop`/`increment`/`scope`/`when`
  convenience methods — parity-additive.
