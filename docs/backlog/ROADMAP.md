# Arvel Roadmap

## Overview

Four epics ported and hardened from the `arvel_old` codebase, rewritten for the current
monorepo architecture. Epics are sequenced by dependency: the core framework hardening epic
must land first, as companion packages rely on its observability and context foundations.

---

## Epic Summary

| # | Epic | File | Stories | Complexity | Priority |
|---|------|------|---------|------------|----------|
| 001 | Core Framework Hardening | `001-epic-core-framework-hardening.md` | 9 | Large | Must |
| 002 | Social Authentication (`arvel-auth-social`) | `002-epic-social-authentication.md` | 5 | Large | Must |
| 003 | Scout-Style Search (`arvel-search`) | `003-epic-scout-search.md` | 4 | Medium | Must |
| 004 | Audit Trail & Activity Log (`arvel-audit`) | `004-epic-audit-activity.md` | 4 | Medium | Should |

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
