# WI-arvel-022 — Context.dehydrate/hydrate must round-trip hidden data

- **Module**: 22 — context (`ContextRepository`, `Context` facade)
- **Complexity**: L2
- **Risk tier**: 2
- **Data classification**: internal
- **Status**: completed

## Problem

`ContextRepository.dehydrate()` returned **only** the visible store and dropped
hidden context; `hydrate()` restored only visible keys and merged instead of
replacing:

```python
def dehydrate(self):  -> dict[str, Any]
    return dict(self._data)            # hidden excluded "by design"

def hydrate(self, data):
    self._data.update(data)            # merge, visible only
```

- **C1 (correctness / Laravel parity)** — in Laravel, `Context::dehydrate()`
  captures **both** `data` and `hidden`, and `hydrate()` restores both. "Hidden"
  means hidden from logs and from `all()`/`get()`, **not** hidden from the queue.
  The Laravel docs' `dehydrating` example proves it:

  ```php
  Context::dehydrating(fn ($c) => $c->addHidden('locale', Config::get('app.locale')));
  Context::hydrated(fn ($c) => $c->hasHidden('locale') && Config::set('app.locale', $c->getHidden('locale')));
  ```

  Arvel's repository docstring framed the exclusion as intentional ("must not
  leave the process"), which misreads Laravel's hidden semantics. A port that
  relies on hidden context surviving a queued job would silently lose it.

## Fix

Match Laravel's shape and replace-on-hydrate semantics:

```python
def dehydrate(self) -> dict[str, dict[str, Any]]:
    return {"data": dict(self._data), "hidden": dict(self._hidden)}

def hydrate(self, payload: dict[str, dict[str, Any]]) -> ContextRepository:
    self._data = dict(payload.get("data", {}))
    self._hidden = dict(payload.get("hidden", {}))
    return self
```

Hidden stays out of `all()`/`get()` and logs — it just travels with the job.
Facade signatures updated to match.

## Acceptance criteria

- `dehydrate()` returns `{"data": {...}, "hidden": {...}}`.
- Hidden keys round-trip: after `worker.hydrate(payload)`, `get_hidden` sees them,
  but `all()` does not.
- `hydrate()` replaces existing state (worker starts from the snapshot).
- Snapshot is decoupled from the live store (later mutations don't change it).
- mypy --strict, pyright, ruff check, ruff format clean; full arvel suite green.

## Out of scope (deferred)

- Wiring context propagation into the queue dispatch/worker path (the methods
  exist and are now faithful, but no auto-dehydrate-on-dispatch hook yet).
- `pull`, `pop`, `increment`/`decrement`, `scope`/`when` convenience methods —
  parity-additive.

## Files

- `packages/arvel/src/arvel/context/repository.py`
- `packages/arvel/src/arvel/context/facade.py`
- `packages/arvel/tests/context/test_context_repository.py` (updated to Laravel contract)
- `packages/arvel/tests/context/test_wi_022_context_dehydrate_hidden.py` (new)
