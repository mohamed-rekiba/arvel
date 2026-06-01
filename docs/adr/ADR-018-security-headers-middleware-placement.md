# ADR-018: `SecurityHeadersMiddleware` — pure-ASGI, in `arvel.http.middleware`

**Status**: Accepted
**Date**: 2026-05-24
**Last reconciled**: 2026-06-01

## Context

The demo shipped a local `SecurityHeadersMiddleware` copy. Every production Arvel app should apply the same security headers without copying code.

## Decision

Ship `SecurityHeadersMiddleware` in `arvel.http.middleware.security_headers` as a **pure-ASGI** middleware (not `BaseHTTPMiddleware`). It injects four headers on every HTTP response:

```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; frame-ancestors 'none'; form-action 'self'
```

All headers use `setdefault` semantics — handler-set values are never overwritten. WebSocket and lifespan scopes pass through unmodified. Every value is configurable via constructor kwargs; `csp=None` suppresses the CSP header, and `path_csp_overrides` maps path prefixes to a per-path CSP (longest matching prefix wins) — useful for serving Swagger UI under a looser policy without weakening the global default.

## Rationale

- **Pure ASGI over `BaseHTTPMiddleware`**: `BaseHTTPMiddleware` buffers the whole response body, breaking `Content-Length` on streaming responses and adding latency. Pure ASGI hooks `http.response.start` directly.
- **`arvel.http.middleware`** is the right home — security headers are a cross-cutting HTTP concern, not tied to auth/i18n/cache.
- **`setdefault`** preserves a route's own headers (e.g. a nonce-based CSP).
- **`frame-ancestors 'none'`** prevents clickjacking; a safe default for APIs and most web apps.

## Current implementation

- Code: `packages/arvel/src/arvel/http/middleware/security_headers.py` (defaults: `_DEFAULT_HSTS_MAX_AGE`, `_DEFAULT_CSP`, `_DEFAULT_REFERRER_POLICY`).
- Docs: `docs-fresh/http/middleware.md`.

## Notes

- **Reconciled**: the shipped default CSP is `default-src 'self'; frame-ancestors 'none'; form-action 'self'` (the original ADR omitted `form-action 'self'`). The `csp=None` and `path_csp_overrides` knobs were added after the original.
