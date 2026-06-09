# Epic: JWT revocation denylist + shared login throttle

## Summary
Make stateless access JWTs revocable and the login throttle shareable across
workers. Deferred finding F5, security path.

**Spec:** `docs/pipeline/specs/WI-arvel-052-jwt-revocation-login-throttle.md`

## Delivered

### Story 1: Access-token revocation denylist — Done
Cache-backed `auth/token_denylist.py` with per-`jti` deny (single-session logout)
and a per-user `iat` cutoff (reset / refresh-reuse → kill all). Tokens gained an
`iat` claim; `AuthService.me` and `JwtGuard.user` reject revoked tokens after the
signature/exp check. Logout denies the presented bearer's `jti`; password reset
and reuse detection call `revoke_all_for_user`. Fails open on cache outage.

### Story 2: Shared login throttle — Done
`ThrottleLoginMiddleware` takes a pluggable `LoginAttemptStore`; pass
`CacheLoginAttemptStore` to share the failed-attempt limit across workers. Tuning
moved to `ThrottleLoginConfig`.

## Security
A logged-out or reset access token stops working immediately instead of riding
out its TTL. Denylist checks fail open so a cache outage degrades to "revocation
stops working" rather than an auth DoS. Shared state lives in the cache (Redis
across workers; default cache is single-process).

## Tests
`tests/test_auth/unit/test_token_denylist.py` (9), revocation cases in
`test_auth_service.py` (3), cache-store cases in `test_throttle_login.py` (2).

## Gates
ruff clean; mypy 0; pyright 0/0; auth + test_auth 270 passed; http + auth 512
passed; mkdocs --strict clean.
