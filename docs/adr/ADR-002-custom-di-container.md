# ADR-002 — Build a custom DI container instead of adopting Dishka/Lagom/Punq

**Status**: Accepted
**Date**: 2026-05-17
**Last reconciled**: 2026-06-01
**Deciders**: Solution Architect (autonomous)
**Scope**: `arvel.container`

---

## Context

Laravel's service container is a defining feature: autowiring from type hints; singleton/scoped/transient lifetimes; contextual binding; tagged bindings; extending (decorating) resolved services; and request/worker-aware scoped resolution. Python has three mature DI containers — Dishka (FastAPI-integrated, scope/component model), Lagom (type-based, mypy-friendly), and Punq (simple type wiring). None covers contextual binding + tagging + extending in one container.

## Options considered

### Option A — Use Dishka

**Pros**: endorsed by FastAPI, community-vetted, sophisticated scopes. **Cons**: its providers/scopes/components mental model differs from Laravel's container/providers/facades; users would learn both; no first-class contextual binding or Laravel-style tagging; API evolution tied to Dishka's roadmap.

### Option B — Use Lagom

**Pros**: smallest footprint, type-based. **Cons**: no contextual binding or tagging — we'd hand-roll most of Laravel's surface anyway.

### Option C — Build our own (chosen)

**Pros**: 100% mappable to Laravel's container surface; owned at the type-checker level so `make[T] -> T` holds under both strict checkers; evolution decoupled from any third party; small, well-bounded module; gives a clean `dep(T)` bridge into FastAPI's `Depends` without dragging in another runtime. **Cons**: we own the resolution algorithm, scopes, and contextual matching.

## Decision

**Option C.** `arvel.container.Container` provides bind/singleton/instance/scoped bindings, autowiring from `__init__` type hints, contextual bindings, tagging, async factories, and scope management. `dep(T)` bridges container resolution into FastAPI dependencies.

## Consequences

- The container is critical infrastructure and carries a high coverage floor (see ADR-011).
- Its behavior is a public contract, documented in the architecture docs.
- Generic-heavy resolution is designed types-first so both strict checkers infer `make[T] -> T`.

## Current implementation

- Code: `packages/arvel/src/arvel/container/`, `packages/arvel/src/arvel/dep.py`.
- Docs: `docs-fresh/architecture/service-container.md`.

## Notes

- The previously-mooted optional "Dishka-compatible adapter" was **not** shipped. The container is non-magical, so raw FastAPI `Depends` remains available for users who prefer it; that is not the blessed path.
