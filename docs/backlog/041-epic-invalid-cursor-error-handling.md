# Epic: A malformed pagination cursor should be a 400, not a 500

## Summary
`cursor_paginate` decodes an opaque `?cursor=` token. A hand-edited, truncated, or
stale token raises `InvalidCursorError` (an `ORMError`) with no HTTP translator, so
it became a `500 INTERNAL_ERROR` and risked leaking the base64/JSON decode reason.
A bad cursor is bad client input — map it to a 400 with a fixed message.

**Module:** ORM pagination · **Spec:** `docs/pipeline/specs/WI-arvel-041-invalid-cursor-error-handling.md`

## Stories

### Story 1: Malformed cursor returns a 400
**As a** client paging with a cursor, **I want** a clear 400 when my cursor token is
malformed, **so that** I can drop it and restart paging instead of seeing a 500.

**Acceptance Criteria**:
- [ ] Given a malformed cursor, when `cursor_paginate` decodes it, then `InvalidCursorError` is raised.
- [ ] Given that error reaches the HTTP layer, when the response is built, then it is a 400 with message `Invalid pagination cursor.`
- [ ] Given the 400 response, when inspected, then it leaks no base64/JSON decode internals.
- [ ] Given a valid `next_cursor`/`prev_cursor` token, when passed back, then paging works unchanged.

**Security Requirements**:
- [ ] Error message is fixed; decode internals never reach the client (A10 — mishandling of exceptional conditions).
- [ ] Bad client input maps to 4xx, not 5xx (correct status semantics).

**Requirement Refs**: SPEC-1
**Priority**: Should · **Complexity**: Small · **Status**: Done

## Dependencies
- Reuses the optional `arvel.database.exceptions` import already in `http_provider`.

## Notes
- The paginators (`paginate`, `simple_paginate`, `cursor_paginate`) were audited and
  found Laravel-aligned; no other defects.
