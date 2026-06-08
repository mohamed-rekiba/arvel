# Epic: Log redaction reaches nested context, not just top-level keys

## Summary
The structured logger's secret redaction must scrub secret-keyed values wherever
they appear in a log line's attributes — inside nested dicts and lists, at any
depth — not only at the top level. Closes an A09 sensitive-data exposure where a
secret nested under a non-secret key (`payload={"password": ...}`) leaked to logs.

**Module:** logging · **Spec:** `docs/pipeline/specs/WI-arvel-033-log-redaction-nested.md`

## Stories

### Story 1: Nested secrets are redacted at any depth
**As a** developer logging structured context, **I want** secret-keyed values
redacted even when nested inside dicts or lists, **so that** I can't accidentally
leak credentials by logging a request body or payload object.

**Acceptance Criteria**:
- [ ] Given `Log.info("e", payload={"password": "x"})`, when the record is emitted, then `payload.password` is `[REDACTED]`.
- [ ] Given a secret nested several levels deep, when emitted, then it is `[REDACTED]`.
- [ ] Given a list of dicts containing a secret key, when emitted, then the secret values are `[REDACTED]` and non-secret entries are untouched.
- [ ] Given a custom `LOG_REDACT_FIELDS`, when a matching key is nested, then it is `[REDACTED]`.

**Security Requirements**:
- [ ] Redaction is fail-closed: the default secret set applies when `LOG_REDACT_FIELDS` is unset.
- [ ] No secret-keyed value at any depth survives to the emitted record.

**Documentation Requirements**:
- [ ] Spec records the divergence from `config._strip_secrets` and the corrected comment.

**Requirement Refs**: SPEC-1
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: Non-secret structure is preserved; gates green
**As a** maintainer, **I want** non-secret nested data passed through unchanged and
the strict type gate clean, **so that** redaction stays a surgical, type-safe change.

**Acceptance Criteria**:
- [ ] Given non-secret nested dicts/lists, when emitted, then the structure and values are unchanged (modulo OTel's leaf-sequence tuple normalization).
- [ ] Given top-level secrets and custom redact sets, when emitted, then behaviour matches WI-019.
- [ ] Given the type gate, when I run mypy --strict and pyright, then zero errors and no new bare `# type: ignore`.

**Requirement Refs**: SPEC-2
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- Builds on WI-arvel-019 (substring secret matching). Picks up its deferred
  "nested-dict redaction" follow-up.

## Notes
- Exception text (`exception.message`/`exception.stacktrace`) is not key-based and
  is left unredacted by design.
- The hint-set difference between the logger and `config` is intentional; only the
  recursion behaviour is unified.
