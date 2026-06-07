# Epic: Doc & CHANGELOG freshness pass

## Summary

The root `CHANGELOG.md`'s `[Unreleased]` block lists three items as pending — route model binding, resource controllers, recursive tree relations — that are already shipped (`routing.py:258–411, 620–751, 1085–1126`; `tests/routing/test_wi055_route_model_binding.py`, `test_wi058_route_resource.py`; `database/orm/relations.py:152–266`). Several site-doc pages and a few `# nosec`/`# noqa` justifications also reference deleted ticket IDs (banned by `humanize-comments.mdc`). This epic is a single cleanup sweep — no behaviour changes.

## Audit reference

`routing audit` (parallel review pass, 2026-06-05) — `[Code Quality]` items "Stale CHANGELOG vs shipped code"; `auth audit` — `[Code Quality]` `key:rotate` tracker-ID reference.

## Stories

### Story 1: Root `CHANGELOG.md [Unreleased]` matches shipped reality

**As a** prospective user reading the README, **I want** the unreleased block to list only the gaps that genuinely remain, **so that** I don't think the project is further behind than it is.

**Acceptance Criteria**:
- [ ] Given `CHANGELOG.md`, when I read `[Unreleased]`, then "Route model binding", "Resource controllers", and "Recursive tree relations" are NOT listed.
- [ ] Given the same block, when I read it, then the real remaining gaps named by the parity audit are listed in priority order: validation rule expansion, HTTP facades (`response()` / `redirect()` / `Http::`), route caching, test fakes (`Queue::fake`, `Notification::fake`, `Http::fake`, `Bus::fake`), `RefreshDatabase` test trait, nested/singleton resource routes.
- [ ] Per-package changelogs are unchanged (release-please owns them).

**Security Requirements**:
- [ ] None.

**Documentation Requirements**:
- [ ] `CHANGELOG.md` updated as above.

**Requirement Refs**: AUDIT-ROUTING-QUALITY-1
**Priority**: Must
**Complexity**: Small
**Status**: Ready

---

### Story 2: Site docs reflect shipped routing surface

**As a** new user reading the docs site, **I want** route model binding, resource controllers, and tree relations to be documented as available with usage examples, **so that** I don't infer they're missing.

**Acceptance Criteria**:
- [ ] Given `docs/site/docs/the-basics/routing.md`, when I read it, then it includes an "Implicit route model binding" section with a code example using a typed parameter resolving to a model.
- [ ] Given the same page, when I read it, then there is a "Resource controllers" section showing `Route.resource()` and `Route.api_resource()` with the seven actions.
- [ ] Given `docs/site/docs/orm/relationships.md` (or the closest equivalent), when I read it, then there is a "Recursive tree relations" section showing `has_many_recursive()` / `with_tree()` against an adjacency-list `Category` model.
- [ ] Each new section links to the relevant test (`test_wi055_*.py`, `test_wi058_*.py`) as the executable spec.

**Security Requirements**:
- [ ] None.

**Documentation Requirements**:
- [ ] As above.

**Requirement Refs**: AUDIT-ROUTING-QUALITY-1
**Priority**: Must
**Complexity**: Medium
**Status**: Ready

---

### Story 3: Code comments and CLI errors don't reference deleted ticket IDs

**As a** maintainer, **I want** `# nosec`, `# noqa`, and user-facing CLI errors to be free of `WI-…` references, **so that** the codebase complies with `humanize-comments.mdc` ("no references to process artifacts in code").

**Acceptance Criteria**:
- [ ] Given a repo-wide grep for `WI-` in `packages/`, when run, then the only hits are in `tests/` (test-id markers, allowed) and `docs/` (audit/backlog tracking, allowed). Source files in `packages/*/src/` have zero process-artifact references.
- [ ] `console/commands/key_rotate.py:56` rephrases its error message without a tracker ID; it points to a config flag or doc page instead.
- [ ] Any `# noqa: <CODE> # WI-xxx`-style comments are rewritten to explain the *reason*, not the ticket.
- [ ] CI grep gate added to `Makefile` or pre-commit: `! rg -n 'WI-[0-9]' packages/*/src/`.

**Security Requirements**:
- [ ] None.

**Documentation Requirements**:
- [ ] `humanize-comments.mdc` already says this; no doc edit needed.

**Requirement Refs**: AUDIT-AUTH-QUALITY
**Priority**: Should
**Complexity**: Small
**Status**: Ready

---

## Dependencies

- None — pure cleanup pass.

## Notes

- Per `enforce-quality-gates.mdc`, the new grep gate must be added to `make pre-commit` / `make ci`, not just docs.
- This epic is intentionally small so it can ship in the same sprint as WI-002 and WI-003.
