# ADR-087 — Email verification: signed URL over DB token

**Date**: 2026-05-21
**Status**: Accepted
**Context**:
**Supersedes**: nothing
**Superseded by**: nothing

---

## Context

WI-027's email verification was a stub: it generated a URL with a query-string
email parameter that didn't match the SPA route shape, so verification 404'd
in production (FB-027-011). WI-028 must ship a real implementation.

Two patterns are common:

1. **DB-backed token** — generate a secret, store its digest in a table
   keyed by user, send the plaintext in the email URL, look up + delete
   on verify. (This is what `password_resets` does.)
2. **Signed URL** — encode `{user_id, email_hash, exp}` into a URL, sign it
   with the app secret, hand to the user, validate on verify. No DB row.

This ADR records the choice for **email verification specifically**. Password
reset stays DB-backed (different threat model — see ADR-088).

## Decision

Email verification uses **signed URLs** via
`itsdangerous.URLSafeTimedSerializer`.

The URL shape is:

```
{APP_URL}/api/auth/email/verify/{URLSafeTimedSerializer.dumps({"id": user.id, "h": sha256(user.email)[:16]})}
```

- Salt: `"arvel.auth.email_verify"` (so the same `APP_KEY` can sign URLs for
  other purposes without cross-purpose verifies).
- TTL: 60 minutes (configurable via `config.auth.verification.ttl_minutes`).
- The hash invariant binds the signature to the email at issue-time — if a
  user changes their email after the URL is issued, the verify fails
  cleanly.

## Drivers

1. **No DB write at issue time.** Registration is the hot path; not adding a
   row makes it faster.
2. **Stateless verify.** A single signature check + 1 SELECT to fetch the
   user. No "does this row exist" lookup.
3. **Already a dependency.** `itsdangerous` is already in our dep tree
   (Pydantic's HMAC requirements + Flask-style sessions in some sub-deps).
   No new install footprint.
4. **Laravel parity.** Laravel's `MustVerifyEmail` flow uses signed URLs
   exactly this way (`URL::temporarySignedRoute(...)`).
5. **Resend is a no-DB-touch operation.** A user clicking "resend
   verification" mints a fresh URL; no rows to clean up.

## Alternatives considered

### A. DB-backed token (`email_verifications` table)

**Pros**:
- Token can be revoked (delete the row).
- Audit trail: who requested verification, how often.

**Cons**:
- Extra table, extra migration, extra cleanup cron.
- Resend creates DB churn.
- Not how Laravel does it — friction with the mental model.

**Rejected**.

### B. Embed the user in JWT and have the app verify

**Pros**:
- Conceptually consistent with the access-token flow.

**Cons**:
- JWTs leak via referrer/history more than opaque base64 (longer, easier
  to spot in logs).
- itsdangerous is purpose-built for this; using JWT here is overkill.

**Rejected**.

## Consequences

### Positive

- One round-trip per verify (signature check + 1 row update).
- Resend is essentially free.
- No per-app `email_verifications` table to maintain.

### Negative

- Revocation requires rotating `APP_KEY` (we accept this; matches Laravel).
- TTL is bound to clock skew — but `URLSafeTimedSerializer` allows up to
  ±60 s skew before rejecting, which is sufficient.

### Neutral

- The kit currently uses query-string-only URLs. The migration produces
  three new SPA routes (`success`, `expired`, `invalid`) for redirect targets,
  but no fundamental SPA changes.

## Validation

- FR-028-18, FR-028-19, FR-028-20, FR-028-21, FR-028-22 in PRD-028 all pass.
- The Mailpit-captured URL parses with the same serializer + key on the
  verify path.
- Tampering any character of the signed payload produces 401.
- Hitting the URL after 61 min produces 401.
