# Epic: Consistent, testable validation error contract

## Summary
Make the validation error envelope uniform across every endpoint and teachable to the
framework's own test helper. One auth endpoint emitted a Pydantic-shaped detail
(`{loc, msg, type}`) while the rest of the framework uses the canonical `{field, issue}`;
and `TestResponse.assert_json_validation_errors` couldn't parse Arvel's own error envelope.

**Module:** validation / http · **Spec:** `docs/pipeline/specs/WI-arvel-004-validation-error-contract.md`

## Stories

### Story 1: Every validation error uses the same detail shape
**As a** client developer, **I want** every 422 to carry detail entries in the same
`{field, issue}` shape, **so that** one parser works against all endpoints instead of
special-casing `reset_password`.

**Acceptance Criteria**:
- [x] Given an invalid/expired reset token, when `reset_password` runs, then the 422 detail entry is `{"field": "token", "issue": ...}`, not `{"loc", "msg", "type"}`.
- [x] Given the auth app's configured handler (RFC 7807), when the error renders, then `exc.details` is passed through verbatim so the canonical shape survives.
- [x] Given no behavior change elsewhere, when the full auth-controller suite runs, then it stays green.

**Security Requirements**:
- [x] None — shape-only change; no information disclosure (the message was already client-facing).

**Documentation Requirements**:
- [x] Spec records that the error-bag (`error.details[]`) and RFC 7807 (`detail[]`) handlers both carry the canonical entry shape.

**Requirement Refs**: SPEC-1
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: The test helper understands Arvel's own error envelope
**As a** framework contributor, **I want** `assert_json_validation_errors` to parse Arvel's
native error envelope, **so that** I can assert field-level validation errors against
framework responses without hand-rolling JSON walks.

**Acceptance Criteria**:
- [x] Given an error-bag body `{"error": {"details": [{"field": ...}]}}`, when the helper runs, then it extracts those field names.
- [x] Given an RFC 7807 body with `detail: [{"field": ...}]`, when the helper runs, then it extracts those field names.
- [x] Given existing FastAPI (`detail[].loc`) and Laravel (`errors{}`) bodies, when the helper runs, then recognition is unchanged.

**Security Requirements**:
- [x] None (test-only utility).

**Documentation Requirements**:
- [x] Helper docstring lists all three supported envelopes.

**Requirement Refs**: SPEC-2, SPEC-3
**Priority**: Should · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001..003.

## Notes
- The greenfield envelope stays `{error:{code,message,details:[{field,issue}]}}` — the fix
  makes it uniform, not Laravel-identical.
- The RFC 7807 `ProblemDetailsHandler` intentionally keeps its `application/problem+json`
  envelope; only the per-item detail shape (now canonical) is shared.
- Deferred follow-ups (separate work items):
  - **F3** — `nullable` doesn't short-circuit other rules (risky for `confirmed`/`same`).
  - **F4** — unknown validation rule soft-fails to the client instead of raising at dev time.
  - **F5** — rules only see the Pydantic-parsed body (no raw input / query / path).
  - **F6** — `exists`/`unique` without an active DB session returns 500.
  - **F-DOC** — `docs/site/docs/the-basics/error-handling.md` RFC 7807 WARNING claims
    `ProblemDetailsHandler` installs no catch-all for unhandled `Exception`s, but
    `register()` does (`problem_details.py` adds `handle_unexpected_problem`). Stale doc;
    out of WI-004 scope (detail shape), worth a docs-correctness pass.
- Harness note: the `password_resets` table only materialises under full-module test
  ordering (the WI-003 F4 schema drift), so the new reset test runs alongside the module's
  other reset tests rather than in isolation.
