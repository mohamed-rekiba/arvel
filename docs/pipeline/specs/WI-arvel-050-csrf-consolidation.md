# WI-arvel-050 — CSRF consolidation + multi-source token

- **Module:** 50 (HTTP/auth — CSRF)
- **Complexity:** L2
- **Risk tier:** 3 (security path)
- **Data classification:** confidential
- **Status:** completed

A WI-043 bucket-3 feature gap, the high-risk one. Arvel shipped two CSRF
middlewares that each defined their own `CsrfMismatchException` with **different
status codes** — `VerifyCsrf` (session double-submit) raised 419, while
`CsrfDoubleSubmitMiddleware` (cookie double-submit) raised 403 — under the same
`CSRF_MISMATCH` code. Two exception classes, two statuses, one concept. Neither
accepted the `X-XSRF-TOKEN` header that SPA clients (Axios) send, and neither
read the `_token` form field that classic HTML posts use.

## Scope

CSRF only. The `TrustProxies` general request-path IP resolution that was bundled
into the same triage line is a distinct concern (its own middleware, its own
config) and is tracked as a separate WI — see the CHANGELOG remaining-gaps list.

## What landed

### One shared exception (419)

`CsrfMismatchException` now lives in `arvel/http/exceptions.py` (419,
`CSRF_MISMATCH`), matching Laravel's `TokenMismatchException` ("Page Expired").
Both middlewares import it. The cookie check moved off its old 403 onto 419.
It's still re-exported from `arvel.http.middleware` and
`arvel.auth.middleware.csrf_double_submit` so existing imports keep working.

### Multiple token sources (Laravel order)

`_submitted_csrf_token(request)` in `http/_middleware_core.py` reads, in order:

1. `X-CSRF-Token` header
2. `X-XSRF-TOKEN` header (the alias Axios sends from the `XSRF-TOKEN` cookie)
3. `_token` field of an `application/x-www-form-urlencoded` body

`CsrfDoubleSubmitMiddleware` (ASGI-native, SPA/JSON flow) accepts the
`X-XSRF-TOKEN` alias too; it stays header/cookie only and doesn't read bodies.

## Design notes

- **419, not 403.** Laravel's token mismatch is 419 and `VerifyCsrf` already used
  it with a "Laravel CSRF parity" note in its test. The 403 on the cookie check
  was the outlier, so consolidation moved it to 419. Greenfield — no shim.
- **Only urlencoded bodies are inspected for `_token`.** JSON and multipart
  (upload) bodies are never buffered just to hunt for a token that belongs in a
  header — that would parse uploads into memory on every POST. Header sources
  cover the SPA/API path; `_token` covers the classic web-form path.
- **No double body consumption.** Starlette caches `request.form()` / `body()`,
  so the downstream FastAPI handler re-reads the same cached parse.
- **Pyright + `callable()`.** `callable()` narrows `Any` to `(...) -> object`,
  which breaks `await`. The form-getter is annotated `Any` and guarded with
  `is not None` instead, so no suppression is needed.

## Tests

- `packages/arvel/tests/http/middleware/test_csrf.py` — added X-XSRF-TOKEN alias,
  `_token` form-field accept, and JSON-body-not-buffered cases.
- `packages/arvel/tests/test_auth/unit/test_csrf_double_submit.py` — 403→419,
  X-XSRF-TOKEN alias accept, exception status assertion.
- `packages/arvel/tests/test_auth/integration/test_controller.py` — refresh CSRF
  mismatch now asserts 419.

## Gates

ruff check clean; `uv run mypy` 0 issues; `uv run pyright` 0/0; http + auth +
test_auth + security suites 528 passed; mkdocs build --strict clean.
