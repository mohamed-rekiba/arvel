# ADR-089 — Refresh-token storage strategy

**Status**: Accepted
**Date**: 2026-05-20

## Context

`JwtGuard` issues short-lived access JWTs. To support API sessions longer than a few minutes without inflating access-token TTLs, we need a refresh mechanism. There are several common shapes:

1. **Long-lived JWTs** — single token, just bump `exp`. Simple, but a leaked token is valid until expiry; revocation requires a denylist or short TTL.
2. **JWT refresh + JWT access** — sign both with the same secret, use a `typ` claim to discriminate. Stateless, but revocation is hard and rotation requires a server-side denylist anyway.
3. **Opaque refresh + JWT access** — random opaque refresh token stored hashed in DB; JWT for access. Server can revoke instantly, rotate cheaply, and never has to validate refresh tokens cryptographically.

## Decision

Adopt option (3). Refresh tokens are:

- **Opaque** — random URL-safe strings (`secrets.token_urlsafe(40)`), ≥40 bytes of entropy.
- **Hashed at rest** — SHA-256 hex digest stored in `refresh_tokens.token`. Plaintext is shown to the client once and never stored.
- **Rotated on use** — by default `JwtGuard.refresh_tokens(...)` revokes the supplied token and issues a fresh pair (configurable via `rotate_refresh=False`).
- **Time-bounded** — stored with `expires_at`; `find_by_hash` returns `None` past expiry or after `revoked_at` is set.
- **Discriminated from access tokens** — `JwtGuard.user` rejects any Bearer JWT whose `typ` claim is not `access`. This blocks refresh-as-bearer attacks even if the application mistakenly returns a refresh JWT instead of an opaque token.

Storage layer:

- Persistence is behind a `RefreshTokenRepository` Protocol (`store`, `find_by_hash`, `revoke`).
- `InMemoryRefreshTokenRepository` ships as a test double and a starting point for simple apps.
- A SQL-backed repository can be added later without API churn.

Migration:

- `packages/arvel/src/arvel/auth/migrations/create_refresh_tokens_table.py` ships the framework stub. Apps copy it (or `arvel make:migration CreateRefreshTokensTable`) into `database/migrations/` to apply.

## Consequences

✅ Server has full control over refresh-token validity (revoke, rotate, audit).
✅ Leaked refresh tokens have a bounded blast radius — rotation invalidates the old one on next use.
✅ DB compromise leaks hashes, not plaintext.
✅ Stateless access tokens preserve scaling story.

⚠️ Refresh requires a DB round-trip. Acceptable: refresh is rare relative to access-token use.
⚠️ Apps must store the refresh token securely on the client (OS keychain, HttpOnly cookie). Documented in `docs/site/docs/authentication.md`.

## Related

- Builds on the precedent set by **ADR-085** (TokenGuard's SHA-256 hashing of personal access tokens).
- Pairs with **JwtGuard's existing protections**: `alg=none` rejected, 32-byte HMAC minimum, signature + `exp` always verified.
