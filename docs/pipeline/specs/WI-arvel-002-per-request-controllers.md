# WI-arvel-002 — Controllers must resolve fresh per request

| | |
|---|---|
| **Module** | routing / http |
| **Complexity** | L2 | **Risk** | Tier 2 | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/002-routing-http.md` (D1, D2) |
| **Review** | `requesting-code-review` — D1 Critical confirmed (both adapters); D2 Minor |

## Problem

`MethodControllerAdapter.build()` and `_invokable_controller_adapter()` instantiate
the controller **once at route-registration time** and close over that single
instance. Every request to the route reuses it, so any per-request state written to
`self` accumulates and bleeds across requests — and across users in a concurrent
async process. Reproduced: three requests to a controller doing `self.calls += 1`
returned `calls = 1, 2, 3` instead of Laravel's `1, 1, 1`.

This is a Laravel-parity violation (Laravel resolves the controller from the
container per request) and a concurrency/correctness hazard (shared mutable state).

Secondary (D2): `database_transaction.py` wrote `except TypeError, ValueError:` —
on Python 3.14 this parses as the tuple `except (TypeError, ValueError):` and works,
but it reads exactly like the removed Python-2 name-binding form in commit/rollback
code.

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | `MethodControllerAdapter` resolves a **fresh** instance per request; per-request `self` state never bleeds across requests (HTTP + adapter unit). | `test_wi002_per_request_controllers.py::test_method_controller_is_fresh_per_request*` | PASS |
| SPEC-2 | Invokable (`__call__`) controllers also resolve a fresh instance per request. | `::test_invokable_controller_is_fresh_per_request*` | PASS |
| SPEC-3 | DI fail-fast preserved: an unresolvable controller dependency still raises at **mount** (`register_with_app`), not on first request. | `test_043_critical_fixes.py::test_invokable_controller_unbound_dependency_raises_resolution_error` (unchanged, green) | PASS |
| SPEC-4 | No behavior regression: constructor DI, shared singleton **deps**, sync methods, signature/path-param flow-through, model-binding + FormRequest coexistence, resource routes. | `test_wi057_controller_di.py`, `test_wi058_route_resource.py`, `test_controller.py`, `test_043_critical_fixes.py` (full, green) | PASS |
| SPEC-5 (D2) | DB-transaction middleware exception tuple parenthesized; rollback/commit behavior preserved (numeric + non-numeric status branches). | `test_database_transaction_middleware.py` (full, green) | PASS |
| SPEC-6 (X-cut: type safety) | mypy --strict + pyright clean; no new `# type: ignore`/`cast`-to-`Any`/`Any` at public boundaries. | `mypy` + `pyright` | PASS (0 errors) |
| SPEC-7 (X-cut: no regression) | Full routing + http suites stay green; ruff clean. | `pytest packages/arvel/tests/routing packages/arvel/tests/http` + `ruff check` | PASS |

## Root-cause fixes

- `routing.py` — `MethodControllerAdapter.build()`: instantiate a **probe** once
  (validates DI wiring at mount → preserves fail-fast; bound-method signature has
  the receiver already stripped, so no fragile `self`/`cls`/`staticmethod`
  handling), then build a handler that resolves a **fresh** instance per request
  and discards the probe. Closure captures `cls`/`action`/`container`, never the
  instance.
- `routing.py` — `_invokable_controller_adapter()`: same probe-then-fresh pattern
  for `__call__` controllers.
- `http/middleware/database_transaction.py` — `except (TypeError, ValueError):`.

## Deliberate design decisions

- **Probe at build time** is intentional: it keeps boot-time DI validation
  (misconfigured controllers fail at startup, not on first traffic) *and* gives a
  receiver-free signature without descriptor introspection. The probe is **never
  used to serve a request** — every request resolves its own instance. (It lingers
  only as `@wraps` metadata on the handler, same single-instance footprint the old
  code already had, but it never handles traffic.)
- Controllers bound via `container.instance(...)` / `singleton(...)` (e.g. the
  kit's stateless `EcommerceAuthController`) still return the same shared object
  from `make()` per request — that is the app's explicit lifetime choice and is
  unchanged. Per-request freshness applies to the default (transient) binding,
  matching Laravel.

## Deferred (tracked, not silent-corrupting)

- `auth/provider._mount_routes` builds framework auth routes via closures that
  capture a controller instance at boot (same shape as D1, different code path).
  The kit disables framework auth auto-routes and binds `AuthController` via
  `instance()` (stateless), so no active bleed. Belongs to the auth module audit.
- No per-request DI child container yet (`scope.py` attaches the root container as
  `request.state.arvel_scope`). `Container.scoped()` bindings are not request-
  isolated. Separate work item.
- Rate-limit parity: `X-RateLimit-Reset` not emitted; limit headers only on
  `Response` returns; `Retry-After` uses decay not `reset_at`. Recorded for the
  rate-limit/throttle work item.
