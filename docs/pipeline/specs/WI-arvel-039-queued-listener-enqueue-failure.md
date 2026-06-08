# WI-arvel-039 — Event dispatcher swallows queued-listener enqueue failures and runs them inline

- **Module:** 39 (events)
- **Complexity:** L2
- **Risk tier:** 2
- **Data classification:** internal
- **Status:** completed

## Audit scope

`arvel/events/` — `dispatcher.py`, `event.py`, `listener.py`, `listener_job.py`,
`listener_registry.py`, `should_queue.py`, `providers/event_service_provider.py`.

## Findings

The dispatch path is otherwise sound:
- Inline listeners are resolved through DI and errors are caught + logged so one bad
  listener doesn't stop the rest (`test_listener_error_does_not_stop_others`).
- `ShouldBroadcast` events route to the broadcast driver after sync listeners.
- Queued listeners serialize through `ListenerJob`, which deserializes via the
  `ListenerRegistry` / `EventRegistry` allowlists (no arbitrary import — A08 covered,
  same posture as WI-009 notifications). Events are frozen Pydantic, auto-registered.

**Defect (fixed): `_dispatch_queued` swallowed all enqueue failures and ran the listener
inline.** The old body wrapped the Bus lookup, `ListenerJob.create`, and `Bus.dispatch`
in one `try/except Exception: pass` (`# nosec B110`), then fell through to an inline run.
So when a queue **was** configured but the broker was down, the failure was swallowed
with no log at all, and a listener explicitly marked `ShouldQueue` ran synchronously in
the publish path — blocking it, and double-running if the enqueue had half-succeeded.
This was the "dispatcher Bus-error log-swallow" deferred under WI-009.

## Fix

Split the two cases in `_dispatch_queued`:
- **No queue configured** (`Bus.manager is None`): keep the documented dev fallback —
  log `shouldqueue_fallback_inline` and run inline so events still fire.
- **Queue configured**: enqueue via `Bus.dispatch`. On failure, `logger.exception(
  "queued_listener_enqueue_failed", ...)` and return — never run inline. The exception
  is caught at the per-listener level (consistent with `_dispatch_inline`) so one broker
  hiccup can't stall the rest of the publish loop.

## Tests

`packages/arvel/tests/test_events/test_dispatcher.py` (+2):
- `test_queued_listener_enqueues_and_does_not_run_inline` — with a stub Bus manager, the
  listener is enqueued and its inline `handle` does not run.
- `test_enqueue_failure_is_logged_not_swallowed_or_inline` — a raising `Bus.dispatch`
  logs `queued_listener_enqueue_failed`, the publish loop doesn't raise, and the listener
  never runs inline.

The existing `test_should_queue_listener_degrades_gracefully_without_bus` still covers the
no-queue inline fallback.

## Deferred (parity-additive, low value)

- Wildcard listeners / `subscribe()` (Laravel `Event::listen('order.*', ...)`).
- Event inheritance dispatch (listeners on a parent event class don't fire for subclasses;
  Arvel matches the exact runtime type).
- Listener return-value halting (`return false` stops propagation in Laravel).

## Gates

ruff check + format clean; mypy 0 issues (1065 files); pyright 0 errors/0 warnings;
events suite 32 passed (30 existing + 2 new).
