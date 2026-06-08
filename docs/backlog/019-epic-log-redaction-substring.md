# Epic: Log redaction catches secret keys by substring

## Summary
The logging redaction net must match credential field names by substring, not
exact name, so common keys like `access_token`, `client_secret`, and
`db_password` never land in logs in cleartext.

**Module:** logging · **Spec:** `docs/pipeline/specs/WI-arvel-019-log-redaction-substring.md`

## Stories

### Story 1: Common secret field names are redacted
**As an** operator, **I want** the logger to redact any field whose name contains
a secret hint, **so that** tokens and passwords never leak into log output even
when the field is prefixed or suffixed.

**Acceptance Criteria**:
- [x] Given a log call with `access_token`/`refresh_token`/`client_secret`/`api_secret`/`db_password`/`proxy_authorization`, when the record is emitted, then each value is `[REDACTED]`.
- [x] Given non-secret fields (`user_id`, `route`, `count`, `username`), when emitted, then their values pass through unchanged.
- [x] Given a custom `LOG_REDACT_FIELDS=pin`, when logging `card_pin`, then it is redacted by substring.

**Security Requirements**:
- [x] A09 — secrets must not be written to logs; redaction fails closed (substring match).

**Documentation Requirements**:
- [x] `docs/site/docs/features/logging.md` documents substring redaction and `LOG_REDACT_FIELDS`.

**Requirement Refs**: SPEC-1 · **Priority**: Must · **Complexity**: Small · **Status**: Done

## Out of scope (deferred)
- Nested-dict redaction (top-level keys only; documented as shallow).
- Log-level default divergence (`OtelLogger` debug vs `ObservabilityConfig` info) — tested/parity design call.
