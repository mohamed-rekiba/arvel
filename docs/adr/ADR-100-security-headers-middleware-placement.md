# ADR-100: `SecurityHeadersMiddleware` — Pure-ASGI, `arvel.http.middleware`

**Status**: Accepted
**Date**: 2026-05-24

## Context

The fullstack Vue demo shipped `SecurityHeadersMiddleware` as a local copy in
`app/http/middleware/security_headers.py`. Every production arvel app should apply
the same four security headers without copying code.

## Decision

Ship `SecurityHeadersMiddleware` in `arvel.http.middleware.security_headers` as a
**pure-ASGI** middleware (not `BaseHTTPMiddleware`).

Default header values (OWASP-aligned):
```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; frame-ancestors 'none'
```

All headers use `setdefault` semantics — handler-set values are never overwritten.
WebSocket and lifespan scopes pass through unmodified.

## Rationale

- **Pure ASGI over BaseHTTPMiddleware**: `BaseHTTPMiddleware` buffers the entire response
  body before processing, causing `Content-Length` mismatches on streaming responses and
  adding latency. Pure ASGI hooks into the `http.response.start` message directly.
- **`arvel.http.middleware`** is the right home — security headers are a cross-cutting HTTP
  concern, not tied to any subsystem (not auth, not i18n, not cache).
- **`setdefault` semantics** preserve existing headers. A route that returns a nonce-based
  CSP for inline scripts won't have it overwritten.
- **`frame-ancestors 'none'` in default CSP**: Prevents clickjacking. Safe default for API
  responses and most web apps.

## Rejected Alternative

`BaseHTTPMiddleware` subclass — simpler to write but buffers streaming responses and
creates `Content-Length` mismatches on SSE or file download endpoints.
