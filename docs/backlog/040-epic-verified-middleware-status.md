# Epic: Verified-email middleware must return 403, not 401, for logged-in users

## Summary
`VerifiedMiddleware` returned 401 both when no user was authenticated and when a logged-in
user's email wasn't verified. The second case is a 403 authorization failure — re-logging-in
won't help; the user must verify their email. Split the two cases.

**Module:** HTTP/auth middleware · **Spec:** `docs/pipeline/specs/WI-arvel-040-verified-middleware-status.md`

## Stories

### Story 1: Correct status for an unverified, logged-in user
**As a** client of a `verified`-guarded route, **I want** a 403 when I'm logged in but my
email isn't verified, **so that** I'm prompted to verify rather than to re-authenticate.

**Acceptance Criteria**:
- [ ] Given a logged-in user with `email_verified_at` null, when the route runs, then `AuthorizationException` (403) is raised.
- [ ] Given no authenticated user, when the route runs, then `UnauthenticatedException` (401) is raised.
- [ ] Given a verified user, when the route runs, then the handler runs.

**Security Requirements**:
- [ ] Status semantics distinguish authentication (401) from authorization (403) on the access-control middleware (A01).

**Requirement Refs**: SPEC-1
**Priority**: Should · **Complexity**: Small · **Status**: Done

## Dependencies
- Uses the existing `http_provider` translators mapping `auth.AuthorizationException` → 403.

## Notes
- The rest of the middleware stack was audited and found sound (Cors, security headers,
  method spoof, throttle, database transaction, signed, CSRF).
- Deferred / separate: CSRF middleware dedup (session 419 vs cookie 403) is a feature-parity
  item (CHANGELOG bucket-3); login throttle is process-local (F5); no TrimStrings/TrustProxies
  middlewares yet (parity-additive).
