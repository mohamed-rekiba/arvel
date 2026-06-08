# WI-arvel-040 — VerifiedMiddleware returns 401 for an authenticated-but-unverified user

- **Module:** 40 (HTTP / auth middleware stack)
- **Complexity:** L2
- **Risk tier:** 2
- **Data classification:** internal
- **Status:** completed

## Audit scope

The HTTP middleware stack: `arvel/http/_middleware_core.py` (Cors, Throttle,
Authenticate, VerifyCsrf), `arvel/http/middleware/` (security_headers, method_spoof,
scope, signed, database_transaction), and `arvel/auth/middleware/` (authenticate, guest,
verified, can, throttle_login, csrf_double_submit).

## Findings

Most of the stack is already hardened by prior WIs and reviewed clean here:
- `Cors` refuses wildcard-origin + credentials; `SecurityHeadersMiddleware` sets
  HSTS/nosniff/Referrer-Policy/CSP with `setdefault` + path overrides.
- `MethodSpoofMiddleware` buffers + replays the body, only rewrites POST form bodies to
  PUT/PATCH/DELETE.
- `ThrottleLoginMiddleware` keys on (email, ip), clears on success (process-local — F5,
  already tracked). `Throttle` uses the fixed-window store (WI-034).
- `DatabaseTransaction` commits on 2xx/3xx, rolls back on exception or ≥400, runs
  after-commit callbacks only on success. `SignedMiddleware`/CSRF use constant-time
  compare (WI-031). Forwarded-IP guards fixed in WI-030.

**Defect (fixed): `VerifiedMiddleware` conflated two failure modes as 401.** It raised
`UnauthenticatedException` (→ 401) both when there was no authenticated user *and* when a
logged-in user's `email_verified_at` was null. The second case is an authorization
failure, not an authentication one: re-authenticating won't fix an unverified email — the
user has to verify it. Laravel's `EnsureEmailIsVerified` returns 403 (or redirects to the
verification notice) for the authenticated-but-unverified case. Returning 401 misleads the
client into a re-login loop (A01-adjacent: wrong status semantics on an access-control
middleware).

## Fix

Split the cases in `VerifiedMiddleware.handle`:
- `user is None` → `UnauthenticatedException` ("Not authenticated.", 401).
- user present but `email_verified_at` falsy → `AuthorizationException` ("Email address is
  not verified.", 403).

The framework already maps `auth.AuthorizationException` → HTTP 403 and
`auth.UnauthenticatedException` → HTTP 401 (`http_provider` translators), so the status
codes land without extra glue.

## Tests

`packages/arvel/tests/auth/test_middleware.py`:
- `test_verified_middleware_blocks_unverified_user_with_403` — asserts the
  authenticated-but-unverified case raises `AuthorizationException` with `status_code == 403`
  (tightened from the previous loose `(UnauthenticatedException, Exception)` raise check).
- `test_verified_middleware_rejects_unauthenticated_with_401` (new) — no user → 401.

## Deferred (parity-additive / separate items)

- CSRF dedup: two CSRF middlewares coexist — session-based `VerifyCsrf` (419, header
  `X-CSRF-Token`) and cookie-based `CsrfDoubleSubmitMiddleware` (403, header
  `X-CSRF-TOKEN`). Consolidating them (and accepting `X-XSRF-TOKEN` / form `_token`) is a
  feature-parity item (CHANGELOG bucket-3), not a defect.
- `ThrottleLoginMiddleware` / login throttle is process-local (F5).
- No `TrimStrings` / `TrustProxies` / `EncryptCookies` middlewares yet (parity-additive).

## Gates

ruff check + format clean; mypy 0 issues (1065 files); pyright 0 errors/0 warnings;
auth suites 254 passed (incl. the 2 updated/added verified-middleware cases).
