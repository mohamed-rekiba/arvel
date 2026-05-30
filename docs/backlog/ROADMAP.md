# Arvel Roadmap

## Overview

The first four epics were ported and hardened from the `arvel_old` codebase, rewritten for the
current monorepo architecture. Epics 005–007 are an Eloquent-parity wave: a five-dimension review
of Arvent against the Laravel source (`repos/lv-app/vendor/laravel`) surfaced gaps across the query
builder, model/attribute layer, and relationships. Epics are sequenced by dependency: the core
framework hardening epic must land first, as companion packages rely on its observability and
context foundations.

---

## Epic Summary

| # | Epic | File | Stories | Complexity | Priority |
|---|------|------|---------|------------|----------|
| 001 | Core Framework Hardening | `001-epic-core-framework-hardening.md` | 9 | Large | Must |
| 002 | Social Authentication (`arvel-auth-social`) | `002-epic-social-authentication.md` | 5 | Large | Must |
| 003 | Scout-Style Search (`arvel-search`) | `003-epic-scout-search.md` | 4 | Medium | Must |
| 004 | Audit Trail & Activity Log (`arvel-audit`) | `004-epic-audit-activity.md` | 4 | Medium | Should |
| 005 | Query Builder Parity | `005-epic-query-builder-parity.md` | 13 | Large | Should |
| 006 | Eloquent Model Parity (Attributes & Lifecycle) | `006-epic-eloquent-model-parity.md` | 14 | Large | Should |
| 007 | Relationship Parity | `007-epic-relationship-parity.md` | 11 | Large | Should |

---

## Delivery Sequence

```
Sprint 1: Epic 001 — Core Framework Hardening
  ├── Story 1: context/ module
  ├── Story 2: Session-scoped log context
  ├── Story 3: Observability auto-wiring + startup logging
  ├── Story 4: BaseService ABC
  └── Story 5: /_health endpoint

Sprint 2: Epic 001 (continued) + Epic 003 begins
  ├── Story 6: Global error handler via Log facade
  ├── Story 7: Graceful shutdown (SIGTERM/SIGINT)
  ├── Story 8: Cache lock enhancements
  ├── Story 9: Lifecycle regression tests
  └── Epic 003 Story 1: Searchable mixin

Sprint 3: Epic 002 + Epic 003
  ├── Epic 002 Story 1: Built-in OAuth providers
  ├── Epic 002 Story 2: Redirect/callback HTTP flow
  ├── Epic 002 Story 3: PKCE enforcement
  ├── Epic 003 Story 2: SearchBuilder fluent API
  └── Epic 003 Story 3: Multi-driver support

Sprint 4: Epic 002 (continued) + Epic 003 + Epic 004
  ├── Epic 002 Story 4: Generic OIDC discovery
  ├── Epic 002 Story 5: Social account linking + install command
  ├── Epic 003 Story 4: Null/collection drivers + SearchFake
  ├── Epic 004 Story 1: Auditable mixin auto-recording
  └── Epic 004 Story 2: Audit entry query API

Sprint 5: Epic 004 (continued)
  ├── Epic 004 Story 3: ActivityRecorder fluent API
  └── Epic 004 Story 4: arvel audit:install command
```

### Eloquent-Parity Wave (Epics 005–007)

This wave is independent of 001–004 and can run in parallel once the team has capacity. Within the
wave, lead with the highest-value, lowest-risk wins, then the foundation-dependent work.

```
Parity Sprint A: highest-value, self-contained wins  [SPRINT COMPLETE]
  ├── 005 Story 7: efficient exists() / doesnt_exist()   [DONE — WI-arvel-001, ADR-123]
  ├── 005 Story 2: nested WHERE groups                   [DONE — WI-arvel-001, ADR-123]
  ├── 005 Story 4: unless / tap                          [DONE — WI-arvel-001, ADR-123]
  ├── 006 Story 7: without_events() + quiet persistence  [DONE — WI-arvel-002, ADR-124]
  └── 006 Story 2: hashed cast + force_fill + unguard    [DONE — WI-arvel-003, ADR-125]

Parity Sprint B: attribute pipeline + write/stream gaps
  ├── 006 Story 1: attribute-level custom cast protocol  [DONE — WI-arvel-005, ADR-127]
  ├── 006 Story 4: cast-aware dirty tracking            [DONE — WI-arvel-006, ADR-128]
  ├── 005 Story 8: write-path completeness (insert_or_ignore, upsert, truncate)
  ├── 005 Story 10: streaming + chunking completeness    [DONE — WI-arvel-007, ADR-129]
  ├── 005 Story 13: clause polish + WHERE predicate engine [DONE — WI-arvel-008, ADR-130]
  └── 005 Story 12: transaction retry on deadlock        [PARTIAL — WI-arvel-004, ADR-126: retry done; imperative begin/commit/rollback deferred]

Parity Sprint C (WI-arvel-009): 005 S1 date/time + S5 LIKE/multi-col + S6 joins [DONE, ADR-131]
Parity Sprint D (WI-arvel-010): 005 S12 imperative begin/commit/rollback [DONE, ADR-126-03]
Parity Sprint E (WI-arvel-011): 005 S8 write-path completeness [DONE, ADR-132]
Parity Sprint F (WI-arvel-012): 005 S3 subquery FROM/JOIN/SELECT [DONE, ADR-133]

Remaining (proceeding autonomously through all epics):
  005: S9 pagination, S11 debug/query-log
  006: S3 encrypted, S5 Attribute descriptor, S6 enum/builtin casts, S8 ModelCollection,
       S9 static events, S10 soft-delete upsert, S11 delete/replicate events, S12 timestamps,
       S13 factory, S14 attribute polish
  007: S1-S11 (morph map → MorphTo → MorphOne/Many → morphed_by_many → of_many → chaperone →
       polymorphic existence → relation-query completeness → aggregates → pivot → defaults)

Parity Sprint C: relationship foundation
  ├── 007 Story 1: morph map foundation
  ├── 007 Story 2: MorphTo inverse relation
  ├── 007 Story 3: MorphOne/MorphMany query + eager integration
  └── 006 Story 8: ModelCollection (load / loadMissing / PK helpers)

Parity Sprint D: relationship breadth + pagination/API parity
  ├── 007 Story 5: of_many / latest_of_many
  ├── 007 Story 6: chaperone
  ├── 007 Story 10: pivot ergonomics
  ├── 005 Story 9: pagination HTTP + JSON parity
  └── 005 Story 3: subquery FROM / JOIN / SELECT
```

---

## Cross-Cutting Dependencies

```
Epic 001 Story 1 (context/)
  └──▶ Epic 001 Story 2 (session logging)
  └──▶ Epic 002 Story 2 (social callback writes user_id to context)
  └──▶ Epic 003 Story 1 (queued search sync hydrates context)
  └──▶ Epic 004 Story 1 (audit actor_id reads from context)

Epic 001 Story 4 (BaseService)
  └──▶ Epic 001 Story 5 (/_health endpoint)
  └──▶ Epic 001 Story 7 (graceful shutdown calls disconnect())

Epic 007 Story 1 (morph map)
  └──▶ Epic 007 Story 2 (MorphTo)
        └──▶ Epic 007 Story 3 (MorphOne/Many integration)
              └──▶ Epic 007 Story 7 (hasMorph / whereHasMorph)
  └──▶ Epic 007 Story 4 (morphedByMany)

Epic 006 Story 7 (without_events)
  └──▶ Epic 006 Story 13 (factory create_quietly)

Epic 007 Story 3 (morph/pivot eager engine)
  └──▶ Epic 006 Story 8 (ModelCollection.load)
```

---

## Packages Created by This Roadmap

| Package | Location | PyPI Name |
|---------|----------|-----------|
| Core enhancements | `packages/arvel/` | `arvel` (existing) |
| Social auth | `packages/arvel-auth-social/` | `arvel-auth-social` |
| Search | `packages/arvel-search/` | `arvel-search` |
| Audit & activity | `packages/arvel-audit/` | `arvel-audit` |

---

## What This Roadmap Explicitly Excludes

- Standalone `arvel-lock` package — lock enhancements stay in `cache/locks.py` (no new deps)
- Generic repository pattern — domain-specific repos via Protocol is the preferred design
- Replacing OTel with structlog — new arvel stays OTel-first
- In-flight request counting / custom drain logic beyond uvicorn's native graceful timeout
- True per-request child DI containers (WI-002) — scope is a separate future work item
