# WI-arvel-031 — Constant-time token guards crash (500) on non-ASCII input

- **Module**: 31 — URL signing + token comparison guards (routing, http CSRF, auth CSRF, maintenance, storage, reverb)
- **Complexity**: L2
- **Risk tier**: 3 (A10 mishandling of exceptional conditions on security-control paths; trivially attacker-triggerable)
- **Data classification**: confidential
- **Status**: completed

## Problem

`hmac.compare_digest` (and its alias `secrets.compare_digest`) raises
`TypeError: comparing strings with non-ASCII characters is not supported` when
either `str` argument contains a non-ASCII character. Six guards compare an
attacker-controlled `str` token against an expected value:

| Site | Attacker input | Intended reject |
|---|---|---|
| `routing.py` `URL.has_valid_signature` | `?signature=` query | 403 (SignedMiddleware) |
| `http/_middleware_core.py` `VerifyCsrf` | `X-CSRF-TOKEN` header | 419 |
| `auth/middleware/csrf_double_submit.py` | `_csrf` cookie / header | 403 |
| `maintenance/middleware.py` | bypass cookie / `?bypass=` | 503 |
| `storage/url_signer.py` `verify` | `?token=` query | 403 |
| `reverb/auth.py` `verify_channel_auth` | client `auth` string | 403 |

Any of these crashes into an unhandled `TypeError` → **500** instead of the
fail-closed rejection, when the caller sends a single non-ASCII byte (e.g.
`?signature=caf%C3%A9`). It doesn't bypass the signature (still fails closed),
but it converts a clean rejection into a server error on security-control paths:
noisy error tracking, possible stack-trace leakage in debug, and a trivial way to
trip alerting/circuit breakers. PHP's `hash_equals` (Laravel's primitive) never
throws — it returns `false`. Arvel diverged.

The cookie session store (`session/stores/cookie.py`) and token abilities
(`auth/guards/token.py`) already compare **bytes**, so they were never affected.

## Repro

```python
URL.has_valid_signature(request_with("signature=caf%C3%A9"))
# TypeError: comparing strings with non-ASCII characters is not supported
```

vs. an ASCII bogus signature, which correctly returns `False`.

## Fix

One shared, fail-safe primitive in `arvel/support/secure_compare.py`:

```python
def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
```

Comparing the UTF-8 bytes keeps the comparison timing-safe (same primitive) while
a mismatch returns `False` instead of raising. All six sites route through it;
now-unused `import secrets` removed from the three CSRF/maintenance modules.

## Acceptance criteria

- A non-ASCII `signature` / CSRF token / bypass cookie / temp-URL token / channel
  auth string returns `False` (or the route's fail-closed status), never a 500.
- Equal/unequal ASCII comparisons behave exactly as before.
- ruff + format, mypy, pyright clean; affected suites green.

## Out of scope (reviewed, no change)

- `session/stores/cookie.py` and `auth/guards/token.py` compare bytes — safe.
- Email-verification (`EmailVerificationService`) uses `itsdangerous` — safe.
- `URL.signed_route` silently drops non-path kwargs (they are neither added to the
  query nor signed). A parity gap vs Laravel's `signedRoute`, tracked separately;
  not a security defect in the current guards.

## Files

- `packages/arvel/src/arvel/support/secure_compare.py` (new)
- `packages/arvel/src/arvel/routing.py`
- `packages/arvel/src/arvel/http/_middleware_core.py`
- `packages/arvel/src/arvel/auth/middleware/csrf_double_submit.py`
- `packages/arvel/src/arvel/maintenance/middleware.py`
- `packages/arvel/src/arvel/storage/url_signer.py`
- `packages/arvel/src/arvel/reverb/auth.py`
- `packages/arvel/tests/support/test_secure_compare.py` (new)
- `packages/arvel/tests/routing/test_wi053_routing_polish.py`
- `packages/arvel/tests/{broadcasting/test_security.py, storage/test_temporary_urls.py, reverb/test_auth.py, http/middleware/test_csrf.py, security/test_http_safety.py}` (guard tests updated to assert `constant_time_equals`)

## Notes

Two pre-existing suite failures are unrelated to this WI and out of scope:
`tests/hardening/test_nosec_annotations.py` (bare `# nosec` codes in untouched
`console/_venv.py`) and `tests/observability/test_wi_030_config.py` (cwd-dependent
skeleton path, flagged in WI-arvel-030).
