# WI-arvel-023 — Application shutdown must drain every provider even when one teardown raises

- **Module**: 23 — application kernel (`Application.shutdown`)
- **Complexity**: L2
- **Risk tier**: 2
- **Data classification**: internal
- **Status**: completed

## Problem

`Application.shutdown()` tore down services best-effort (log and continue) but
tore down **providers** fail-fast — the first failing `provider.shutdown()`
re-raised immediately and aborted the loop:

```python
for service in reversed(self._services):
    try:
        await service.disconnect()
    except Exception as exc:   # logged, continue
        Log.error(...)
for inst in reversed(self._provider_instances):
    try:
        await inst.shutdown()
    except Exception as exc:
        raise ShutdownError(type(inst), exc) from exc   # strands the rest
self._booted = False
```

Two problems, both biting during the ASGI lifespan's `finally: await shutdown()`:

- **C1 (robustness / resource leak)** — providers shut down in reverse order:
  `Console → user providers → Scheduler → Http → Database → …`. If any provider
  ahead of `DatabaseServiceProvider` raises, `DatabaseServiceProvider.shutdown()`
  (`await engine.dispose()`) never runs → the connection pool leaks on every
  graceful shutdown. The asymmetry with the services loop right above it (which
  is correctly best-effort) made this an obvious inconsistency.
- **C2 (stuck state)** — because the raise happened before `self._booted = False`,
  the app stayed marked booted. A retry would re-run the *whole* teardown,
  double-disconnecting services and re-shutting-down providers that already ran.

Boot is correctly fail-fast (a half-booted app should not serve traffic).
Teardown should be the opposite: drain everything, then surface the failure.

## Fix

Drain all providers, flip `_booted`, then re-raise the first failure:

```python
first_failure: tuple[type[ServiceProvider], BaseException] | None = None
for inst in reversed(self._provider_instances):
    try:
        await inst.shutdown()
    except Exception as exc:   # drain the rest; first failure re-raised below
        Log.error("provider.shutdown_failed", exc=exc, provider=type(inst).__qualname__)
        if first_failure is None:
            first_failure = (type(inst), exc)

self._booted = False
if first_failure is not None:
    provider_cls, original = first_failure
    raise ShutdownError(provider_cls, original) from original
```

`ShutdownError` (public API) still raises on failure, so callers that catch it
keep working — but now every provider got its turn and `_booted` is always
cleared.

## Acceptance criteria

- A failing provider does not strand providers after it in the reverse-shutdown
  order (e.g. the DB engine still gets disposed).
- `shutdown()` still raises `ShutdownError` whose `.provider` is the first
  failing provider.
- `_booted` is `False` after shutdown even when a provider raised; a second
  `shutdown()` is a no-op.
- mypy --strict, pyright, ruff check, ruff format clean; full arvel suite green.

## Out of scope (deferred)

- Aggregating *all* provider failures (e.g. `ExceptionGroup`) — first-failure is
  enough to surface the problem; the rest are logged.
- `environment(*names)` membership-check overload (Laravel parity-additive).

## Files

- `packages/arvel/src/arvel/application/application.py`
- `packages/arvel/tests/application/test_wi_023_shutdown_drains.py` (new)
