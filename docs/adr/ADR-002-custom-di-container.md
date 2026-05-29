# ADR-002 — Build a custom DI container instead of adopting Dishka/Lagom/Punq

**Date**: 2026-05-17
**Status**: Accepted
**Deciders**: Solution Architect (autonomous)
**Scope**: `arvel.container` package

---

## Context

Laravel's service container is one of its defining features. It supports:

1. Auto-wiring from type hints
2. Singleton / scoped / transient lifetimes
3. **Contextual binding** ("When `EmailController` asks for `Mailer`, give it the Resend mailer")
4. **Tagged bindings** (`tag([SmsChannel, EmailChannel, …], "notification.channels")` → `tagged("notification.channels")` returns an iterable)
5. **Extending bindings** (decorate an existing resolved service)
6. Scoped resolution that's request-aware (for HTTP) and worker-aware (for queues)

Python has three mature DI containers we evaluated:

- **Dishka** — Modern, FastAPI-integrated, scope-aware, components/providers concept, growing community. Now recommended in FastAPI's own DI documentation (PR #13628).
- **Lagom** — Type-based auto-wiring, strong mypy, zero-config.
- **Punq** — Simple type-based wiring.

None of them fully cover **all** of Laravel's features, especially contextual binding + tagging + extending in one container.

## Options considered

### Option A — Use Dishka as the container

**Pros**: Recently endorsed by FastAPI; community-vetted; scope/component model is sophisticated.
**Cons**:
- Dishka's mental model (providers + scopes + components) is different from Laravel's (container + service-providers + facades). Marrying the two would force users to learn *both*.
- Dishka doesn't have first-class contextual binding (it has multiple-component activation, which is close but not identical).
- Dishka doesn't have tagging in Laravel's sense (you'd hand-roll it).
- Hard to evolve API independently of Dishka's roadmap.

### Option B — Use Lagom as the container

**Pros**: Smallest mental footprint; type-based; mypy-friendly.
**Cons**: Doesn't support contextual binding or tagging at all; we'd be hand-rolling 60% of Laravel's container surface anyway.

### Option C — Build our own container (chosen)

**Pros**:
- 100% mappable to Laravel's container API and feature set.
- Owned at type-checker level — we can guarantee `make[T] -> T` works under `mypy --strict` and `pyright --strict`.
- Internal evolution decoupled from any third-party container's roadmap.
- Surface is small (~500 LOC + tests) — not the kind of thing that justifies a dependency.
- Provides a clean `arvel.dep(T)` bridge into FastAPI's `Depends` without dragging in another container's runtime.

**Cons**:
- We write and maintain the code (mitigated by it being a small, well-bounded module).
- Have to do our own design work on resolution algorithm, scopes, contextual matching (already done in SAD-001 §2.1).
- Users who'd prefer Dishka still can — `Container` is non-magical and can be sidestepped via raw `Depends` — but that's not the blessed path.

## Decision

**Option C.** Build `arvel.container.Container` per SAD-001 §2.1 and PRD-001 §FR-001-010–016.

The container provides a `Dishka`-compatible adapter (optional, post-1.0) for users who want Dishka's scope semantics; this gives an upgrade path without committing the framework to it.

## Consequences

- The container is critical infrastructure — it gets the most rigorous test coverage in this WI (≥ 95%).
- The container's behavior is documented as a public contract in `docs/api/foundations-api.md`.
- We commit to typing-test discipline: every public method has an `assert_type` test.
- Performance budget NFR-001-001 applies to *our* container, not a third-party benchmark.

## References

- SAD-001 §2.1 (resolution algorithm, performance notes).
- Laravel docs: Service Container (illuminate/container).
- Dishka FastAPI integration: https://dishka.readthedocs.io/en/latest/integrations/fastapi.html
- Lagom: https://lagom-di.readthedocs.io/en/stable/
