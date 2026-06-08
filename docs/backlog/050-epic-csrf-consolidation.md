# Epic: CSRF consolidation + multi-source token

## Summary
Unify the two CSRF middlewares behind one `CsrfMismatchException` (419) and accept
the token sources Laravel does (WI-043 bucket-3 gap, high-risk security path).
TrustProxies (general request-path IP resolution) is split out as its own WI.

**Spec:** `docs/pipeline/specs/WI-arvel-050-csrf-consolidation.md`

## Delivered

### Story 1: One shared exception — Done
`CsrfMismatchException` (419, `CSRF_MISMATCH`) now lives in
`arvel.http.exceptions`. Both `VerifyCsrf` (session) and
`CsrfDoubleSubmitMiddleware` (cookie) import it; the cookie check moved 403→419.
Re-exported from the old locations so imports don't break.

### Story 2: Multiple token sources — Done
Submitted token resolved in Laravel's order: `X-CSRF-Token` header, `X-XSRF-TOKEN`
header (Axios alias), then the `_token` field of an urlencoded form body.
`VerifyCsrf` does all three; the ASGI cookie middleware adds the `X-XSRF-TOKEN`
alias (header/cookie only — no body buffering).

## Not in scope (own WI)
General-purpose `TrustProxies` request middleware so the throttle key / logging
see the real client behind a load balancer. Trusted-proxy resolution already
exists for observability/reverb (`observability/forwarded.py`); wiring it onto the
app request path is its own security-path change.

## Tests
`tests/http/middleware/test_csrf.py`, `tests/test_auth/unit/test_csrf_double_submit.py`,
`tests/test_auth/integration/test_controller.py`.

## Gates
ruff clean; mypy 0; pyright 0/0; http + auth + test_auth + security suites 528
passed; mkdocs --strict clean.
