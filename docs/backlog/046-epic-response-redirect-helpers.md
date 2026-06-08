# Epic: response() / redirect() HTTP helpers

## Summary
Add Laravel-style `response()` and `redirect()` helpers (WI-043 bucket-3 gap).
Additive module — handlers can still return any Starlette response.

**Spec:** `docs/pipeline/specs/WI-arvel-046-response-redirect-helpers.md`

## Delivered

### Story 1: response() builders — Done
`response().json/text/make/no_content` for the common shapes.

### Story 2: redirect() + named routes + back — Done
`redirect(to)`, `to_route(name, **params)` (via `routing.route`), `back(request)`
(Referer with fallback).

### Story 3: redirect-with-flash — Done
`redirect(...).with_(request, key=value)` flashes into the session before
redirecting; no-op without session middleware.

## Tests
`packages/arvel/tests/http/test_wi046_response_redirect.py` — 12 cases.

## Gates
ruff clean; mypy 0 (1069 files); pyright 0/0; http suite 209 passed; mkdocs
--strict clean.
