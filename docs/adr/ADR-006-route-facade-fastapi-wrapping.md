# ADR-006 — Route facade wraps FastAPI APIRouter, group state in a ContextVar stack

**Date**: 2026-05-17
**Status**: Accepted
**Deciders**: Solution Architect (autonomous)
**Scope**: `arvel.routing`

---

## Context

Laravel's `Route::get(...)` and `Route::group(...)` are module-level facades backed by a global `Router` singleton. Group state (prefix, middleware, name prefix) stacks during the `group(...)` callback and unstacks on exit.

In Python on FastAPI, we have three plausible shapes:

1. Use FastAPI's `APIRouter` directly; expose `app.routes.add(...)` style — no facade.
2. Build our own router from scratch on Starlette routes.
3. **Wrap** `APIRouter` with a thin facade that buffers route declarations during the module-import phase and flushes them onto a `FastAPI` instance at boot.

## Decision

Adopt option 3. `arvel.routing.Router` wraps `fastapi.APIRouter`. The `Route` facade is a module-level proxy to a single `Router` instance. Group state lives in a `contextvars.ContextVar` stack so nested `with Route.group(...)` calls compose correctly and remain thread/async-safe.

```python
# pseudo-impl
_router: Router = Router()
_group_stack: ContextVar[tuple[GroupFrame, ...]] = ContextVar("_group_stack", default=())

def get(path: str, **kw):
    def deco(handler):
        _router.add_route("GET", _resolve_path(path), handler, **_resolve_kw(kw))
        return handler
    return deco

@contextmanager
def group(*, prefix="", middleware=(), name=""):
    frame = GroupFrame(prefix=prefix, middleware=tuple(middleware), name=name)
    token = _group_stack.set(_group_stack.get() + (frame,))
    try:
        yield
    finally:
        _group_stack.reset(token)
```

`Router.register_with_app(fastapi)` walks the buffered routes and calls FastAPI's `add_api_route` for each, preserving:
- Composed paths from the group stack.
- Composed middleware (per-route + per-group) as a `Depends(...)` chain that runs the Arvel `Pipeline`.
- Composed names.

## Why option 3

- We don't lose any of FastAPI's machinery (OpenAPI generation, dependency injection, response validation).
- Group composition stays clean — no global mutable dict, no thread-safety surprises.
- The facade gives us the Laravel DX without forcing users to think about routers.
- We can extend the facade with Laravel niceties (`Route.resource`, `Route.controller`) later without changing the underlying mounting.

## Why not direct APIRouter

- FastAPI's `APIRouter` doesn't compose group state through context managers — you have to keep building new routers and including them. That's not the Laravel mental model.
- Per-route middleware in FastAPI uses `Depends` only; we want a `Middleware` protocol with `await call_next(request)` semantics. Wrapping lets us provide both.

## Why not building from scratch on Starlette

- Loses FastAPI's OpenAPI integration — would have to rebuild it.
- Loses the FastAPI ecosystem (deps, validators, response models) that our users want.
- Violates constitution Article II.1 (integrate, don't replace).

## Consequences

- Routes are buffered until `app.boot()` runs `HttpServiceProvider.boot()` which calls `register_with_app(fastapi)`. **Implication**: importing `app.py` is side-effect-free except for the buffering; nothing hits the network.
- The `ContextVar` stack means routes declared from a background thread WITHOUT the right context will land at the root group. Documented: route declaration is import-time only.
- Tests can call `Router.reset()` to clear buffered routes between cases.

---

## Cross-references

- PRD-002: FR-002-001, FR-002-002, FR-002-003
- SAD-002 §3 (Routing component)
