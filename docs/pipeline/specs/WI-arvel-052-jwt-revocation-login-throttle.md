# WI-arvel-052 — JWT revocation denylist + shared login throttle

- **Module:** auth
- **Complexity:** L2
- **Risk tier:** 3 (security path)
- **Data classification:** confidential
- **Status:** completed

Deferred finding **F5**: "access-JWT has no revocation denylist; login throttle
is process-local." Two related "stateless / process-local needs shared state"
gaps in auth.

## Problem

### F5a — access JWT can't be revoked

The access token is a stateless JWT (`typ=access`, default 15 min). It carried a
`jti`, but nothing checked it. So:

- **Logout** deleted the refresh row but left the current access token working
  until `exp` — the whole access TTL after the user logged out.
- **Password reset** and **refresh-token-reuse detection** revoked only refresh
  rows; an attacker's outstanding access token survived until `exp`. That's the
  worst window to leave open during account-compromise recovery.

### F5b — login throttle is process-local

`ThrottleLoginMiddleware` counted failed `(email, ip)` attempts in a per-process
dict, so N workers gave an attacker N× the attempts and a restart reset the
counter.

## What landed

### `auth/token_denylist.py`

A Cache-backed denylist with two mechanisms (logout vs. "kill everything" have
different semantics):

- `deny_token(jti, expires_at_epoch)` / `is_token_denied(jti)` — deny one token
  until it would have expired anyway (TTL self-cleans). Single-session logout.
- `revoke_all_for_user(user_id, ttl_seconds)` / `revoked_before_for_user` — a
  per-user `iat` cutoff. Any token issued before it is rejected. Password reset
  and reuse detection.
- `is_revoked(jti, subject, issued_at)` — the combined check both decoders call.

### Wiring

- Access tokens gained an `iat` claim — `AuthService.issue_access_token` and
  `JwtGuard._encode`.
- `AuthService.me` and `JwtGuard.user` call `is_revoked` after the
  signature/exp/typ checks; revoked → `InvalidCredentialsError` / `None`.
- `AuthService.logout(refresh_token, access_token=None)` denies the presented
  token's `jti`; the controller passes the bearer. Still idempotent.
- `AuthService.refresh` reuse path and `PasswordService.reset` call
  `revoke_all_for_user` (the latter gained an `access_ttl`, wired from
  `config.jwt.ttl_seconds` in the provider).

### Login throttle

`ThrottleLoginMiddleware` takes a pluggable `LoginAttemptStore`
(`count`/`increment`/`reset`). `InMemoryLoginAttemptStore` is the default;
`CacheLoginAttemptStore` shares the limit across workers via the cache. Tuning
moved into `ThrottleLoginConfig` (the constructor was at 6 args — options struct
per the coding standard).

## Design notes

- **Fail open.** If the Cache facade isn't bound or errors, the denylist check
  reports "not revoked" rather than rejecting every request — a cache outage
  must not become an auth DoS. This is the standard JWT-denylist tradeoff.
  `deny_*` no-op with a warning when the cache is down.
- **Shared on Redis, single-process on the default cache** — same caveat as
  `Cache.lock`. Documented.
- **Logout isolates sessions.** Denying just the presented `jti` means logging
  out one device leaves the user's other sessions alone; reset/reuse use the
  per-user cutoff to kill all.
- **Missing `iat` + a user cutoff → revoked.** A token we can't date doesn't get
  the benefit of the doubt once the user asked to end their sessions.
- **Login-throttle store is opt-in.** Default behavior unchanged; the cache
  store isn't auto-wired (the middleware isn't auto-mounted either).

## Tests

- `packages/arvel/tests/test_auth/unit/test_token_denylist.py` (9): deny/peek,
  expired-token clamp, empty `jti`, user cutoff, `is_revoked` by jti and by
  cutoff (old vs. new token), missing-`iat` rule, no-cutoff, fail-open unbound.
- `test_auth_service.py` (3): logout revokes the presented token; logout isolates
  other sessions; logout works with no cache bound.
- `test_throttle_login.py` (2): cache store shares the counter across two
  middleware instances; success clears the shared counter.

## Gates

ruff clean; `uv run mypy` 0 issues; `uv run pyright` 0/0; auth + test_auth suites
270 passed; mkdocs build --strict clean.
