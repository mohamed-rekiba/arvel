# ADR-082: PathGenerator resolved via DI container with fallback

**Date**: 2026-05-24
**Status**: Accepted

## Context

`DefaultPathGenerator` is currently hard-coded throughout `arvel-image`. Spatie's
`ImageServiceProvider` binds a custom `PathGenerator` in the container; the runtime resolves
it. Our implementation ignores custom bindings, making `PathGenerator` customisation silently
ineffective.

## Decision

Introduce a single `_resolve_path_generator()` helper:

```python
def _resolve_path_generator() -> PathGenerator:
    from arvel.container import app
    return app.make(PathGenerator, default=DefaultPathGenerator())
```

All call sites that previously wrote `DefaultPathGenerator()` call this helper instead.

## Consequences

- Developers can bind a custom `PathGenerator` in any `ServiceProvider` and it will be used.
- If the container is not initialised (unit-test context without app bootstrap), the fallback
  `DefaultPathGenerator()` is used — existing tests pass without change.
- `app.make` is a lightweight dict lookup; no measurable overhead.
