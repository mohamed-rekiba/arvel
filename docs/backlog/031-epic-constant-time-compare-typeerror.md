# Epic: Token-comparison guards crash (500) on non-ASCII input

## Summary
Six security guards compare an attacker-controlled `str` token using
`hmac.compare_digest` / `secrets.compare_digest`, which raises `TypeError` on
non-ASCII input. A single non-ASCII byte (e.g. `?signature=caf%C3%A9`, a CSRF
header, a maintenance bypass cookie) turns the intended fail-closed rejection
(403/419/503) into an unhandled **500**. The fix routes every site through one
timing-safe primitive that compares UTF-8 bytes and returns `False` instead of
crashing — matching PHP/Laravel `hash_equals`.

**Module:** routing + http/auth CSRF + maintenance + storage + reverb · **Spec:** `docs/pipeline/specs/WI-arvel-031-constant-time-compare-typeerror.md`

## Stories

### Story 1: Malformed signature/token never crashes the guard
**As an** operator relying on signed URLs, CSRF, maintenance bypass, temporary
storage URLs, or channel auth, **I want** a malformed (non-ASCII) token to be
rejected cleanly, **so that** an attacker can't turn a 403/419/503 into a 500 by
sending one odd byte.

**Acceptance Criteria**:
- [ ] A non-ASCII `signature` query value → 403 (SignedMiddleware), not 500.
- [ ] A non-ASCII CSRF header/cookie → 419/403, not 500.
- [ ] A non-ASCII maintenance bypass cookie/query → 503, not 500.
- [ ] Non-ASCII temp-URL token and reverb channel-auth strings return `False`.

**Security Requirements**:
- [ ] Comparison stays timing-safe (UTF-8 bytes via `hmac.compare_digest`).
- [ ] No security bypass introduced — mismatches still return `False` (A10).

### Story 2: One shared timing-safe primitive
**As a** maintainer, **I want** a single `constant_time_equals` helper used by all
str/str token comparisons, **so that** the non-ASCII crash can't reappear per-site.

**Acceptance Criteria**:
- [ ] `arvel.support.secure_compare.constant_time_equals` exists and is the only
      path for attacker-facing string token comparison.
- [ ] Now-unused `import secrets` removed from the CSRF/maintenance modules.

**Requirement Refs**: C1 (non-ASCII `compare_digest` crash across 6 guards)
**Priority**: Must · **Complexity**: Small · **Status**: Done
