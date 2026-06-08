# Epic: Feature-gap bucket-3 triage (CHANGELOG [Unreleased])

## Summary
The CHANGELOG `[Unreleased]` "remaining priority gaps" list had drifted: two
entries were already implemented (needs-based CLI bootstrap, `openapi:export
--output FILE`), one over-counted landed validation rules, and one referenced a
nonexistent `docs/backlog/ROADMAP.md`. Triaged every line against the codebase,
moved the landed items, and ranked the genuine gaps so each becomes a focused WI.

**Spec/analysis:** `.context/research/043-feature-gap-bucket3-triage.md`

## Already landed (verified, removed from "remaining")
- Needs-based CLI bootstrap — `CliSubsystem` `requires` per command; only those
  subsystems boot; non-HTTP commands skip routing + banner.
- `openapi:export --output FILE` — file/stdout, YAML/JSON, status on stderr.
- 32 validation rules (the loose "~25 missing" line over-counted).

## Genuine remaining gaps (each → its own future WI)

### Story 1: Outbound `Http::` facade + `Http::fake`
**Priority**: Could · **Complexity**: Large · **Risk**: Medium · **Status**: Backlog
First-party HTTP client over httpx2 with a fake/record mode and `assert_sent`-style
assertions, mirroring `Bus.fake()` / `Notification.fake()`.

### Story 2: `response()` / `redirect()` helpers
**Priority**: Could · **Complexity**: Medium · **Risk**: Low-Med · **Status**: Backlog
`response()` JSON/text/no-content builders; `redirect()` with session flash
(`->with()`), `->route()`.

### Story 3: Route caching `route:cache` / `route:clear`
**Priority**: Could · **Complexity**: Med-Large · **Risk**: Medium · **Status**: Backlog
`optimize` already stubs it pending a `RouteCollection` serializer.

### Story 4: More validation rules (recommended first)
**Priority**: Should · **Complexity**: Medium · **Risk**: Low · **Status**: Backlog
`date`, `bail`, conditional (`required_if`/`sometimes`), nested/wildcard
(`items.*.id`), custom-rule registration, `Rule.in_()`/`Rule.unique()` builders.

### Story 5: CSRF consolidation + `TrustProxies` middleware
**Priority**: Should · **Complexity**: Medium · **Risk**: High (security path) · **Status**: Backlog
Consolidate the two CSRF middlewares (session 419 / cookie 403), accept
`X-XSRF-TOKEN` + form `_token`, add a general request-path `TrustProxies`
middleware. Tier 3 — own WI **with security gates** (do not auto-pass).

### Story 6: `STORAGE_LOCAL_SERVE` local file serving
**Priority**: Could · **Complexity**: Small-Med · **Risk**: Low · **Status**: Backlog
Laravel `serve => true` parity for the local disk.

## Notes
- These are features, not defects — out of scope for the autonomous audit loop,
  which fixes defects. Each needs a planned WI; #5 must not be one-shot.
