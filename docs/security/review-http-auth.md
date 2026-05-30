# Security Review — HTTP Auth

Area: HTTP authentication and authorization middleware.

## Scope

JWT validation, bearer token parsing, CSRF double-submit cookie pattern, session management,
and per-request permission checks in the HTTP layer.

## Findings

No critical or high findings. All authentication paths validate token signature, issuer,
audience, and expiration before granting access. The CSRF middleware enforces the
double-submit cookie pattern on mutating requests and exempts only explicitly listed paths.

## Controls Verified

- JWT claims validated: `exp`, `iss`, `aud`, signature
- Bearer token extracted from `Authorization` header only (no query-param fallback)
- CSRF double-submit enforced on POST/PUT/PATCH/DELETE
- Rate limiting applied at the gateway layer
- Unauthenticated requests return 401; insufficient permissions return 403

## Next Review

Revisit when adding OAuth2 authorization-code flow or introducing new exempt paths.
