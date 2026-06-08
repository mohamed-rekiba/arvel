# Epic: Session regeneration destroys the old store record

## Summary
`SessionData.regenerate()` rotated the session id but never destroyed the old record, and the
`StartSession` middleware had no destroy step. `SessionGuard.login()` calls `regenerate()` "to
prevent session fixation," yet the pre-login session stayed valid in the backend (with its
cart/CSRF/flash payload) until GC. Laravel's auth login uses `migrate(true)`, which deletes the old
session. Regenerate now queues the old id and the middleware destroys it on response.

**Module:** session · **Spec:** `docs/pipeline/specs/WI-arvel-011-session-regenerate-destroy.md`

## Stories

### Story 1: Regenerating the session id invalidates the old one
**As a** user who logs in, **I want** my pre-login session to be destroyed when the id rotates,
**so that** the old session can't outlive the rotation in the backend store.

**Acceptance Criteria**:
- [x] Given a returning visitor with an existing session, when they log in (which calls `regenerate()`), then the old session id is removed from the store.
- [x] Given a regenerated session, when the response finishes, then the new id holds the data and the auth marker.
- [x] Given the cookie driver (whose `destroy` is a no-op), when regenerate runs, then no error occurs.

**Security Requirements**:
- [x] The old session record is destroyed (defense-in-depth against fixation), matching Laravel `migrate(true)`.
- [x] The destroy bookkeeping is never serialized into the session payload.

**Documentation Requirements**:
- [x] `docs/site/docs/features/session.md` notes that `regenerate()` destroys the old record on response.

**Requirement Refs**: SPEC-1, SPEC-2, SPEC-3, SPEC-4
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: Existing session behavior is unchanged
**As an** application developer, **I want** session persistence, flash aging, and the existing
fixation test to keep working, **so that** the destroy fix is purely additive.

**Acceptance Criteria**:
- [x] Given normal requests, when the session is read/written across requests, then persistence and flash aging behave as before.
- [x] Given `SessionGuard.login()`, when called, then it still calls `regenerate()` (unchanged signature) and the existing safety test passes.

**Security Requirements**:
- [x] None beyond Story 1.

**Documentation Requirements**:
- [x] Covered by the regenerate doc section.

**Requirement Refs**: SPEC-5
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001..010.

## Notes
- The auth login path (`SessionGuard.login`) is the real-world trigger; the kit exercises it on web login.
- Deferred follow-ups (separate work items):
  - **Cookie driver ↔ StartSession** — the encrypted-cookie payload is never emitted on the standard
    middleware path (`read_from_cookie`/`last_written_cookie` unused). Larger integration change.
  - **`invalidate()`** — flush + new id + destroy old as a single call (parity-additive).
  - **Flash `get()` shadowing** — `get()` checks `_FLASH_OLD` before regular data (Minor).
  - **Parity-additive** — `pull()`, `increment`/`decrement`, old-input helpers.
