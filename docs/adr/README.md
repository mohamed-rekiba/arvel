# Architecture Decision Records

Decisions that shaped the Arvel framework and its companion packages, grouped by subsystem. The catalog is now compact: one ADR per cohesive subsystem, with the original per-decision records folded into `§` sections inside their canonical record.

Last reconciled: 2026-06-07. **WI-arvel-006** added three companion-package ADRs (`arvel-audit`, `arvel-oauth`, `arvel-search`) plus SAD-005 (CLI runtime architecture). These were the three shipped companion packages that had user-facing docs but no architecture record; the ADRs document real decisions distilled from package source, not aspirational design.

**WI-arvel-005** (2026-06-07) consolidated the original catalog from 131 numbered ADRs to 22 by merging every README section into a single ADR. Each merged ADR's `## Subsumes` block lists the original ADRs it absorbs and where each one lives now (`§ N`). The earlier consolidation pass is still documented in the affected ADR:

- WI-arvel-003 (2026-06-05) merged the seven `arvel-image` ADRs (former 132, 133, 134, 135, 138, 139, 140) and compact-renumbered two trailing ADRs. That work is now ADR-020.

Next free ADR number is **026**.

## Foundation & quality

| ADR | Subject | Decisions absorbed |
|---|---|---|
| [ADR-001](ADR-001-foundation.md) | Foundation & Project — stack, DI, monorepo, packaging, layout, route loader, docs site | 7 (former 001–007) |
| [ADR-002](ADR-002-quality-and-testing.md) | Quality & Testing — type-checker parity, gate enforcement, suppression floor, per-module coverage, test-app context manager | 5 (former 008–012) |

## HTTP

| ADR | Subject | Decisions absorbed |
|---|---|---|
| [ADR-003](ADR-003-http-layer.md) | HTTP Layer — route facade, OpenAPI opt-in, two-tier middleware, rate-limit store, bridge exemption, security headers, exception handler, scope wiring | 8 (former 013–020) |

## Arvent (ORM)

| ADR | Subject | Decisions absorbed |
|---|---|---|
| [ADR-004](ADR-004-arvent-model.md) | Arvent — Model & ActiveRecord layer (mixin on SQLAlchemy, MappedAsDataclass, clean syntax, metaclass forwarding, ModelCollection) | 5 (former 021, 022, 023, 024, 028) |
| [ADR-005](ADR-005-arvent-query-builder.md) | Arvent — Query Builder (write ops, table QB, Collection, kwarg shorthand, predicates, conditional groups, write-path completeness, subqueries, fixes, streaming, pagination, debugging, helpers, FTS, transactions, recursive CTE) | 18 (former 025–027, 029–043) |
| [ADR-006](ADR-006-arvent-schema-and-migrations.md) | Arvent — Schema & Migrations (DSL → Alembic, runner, reversibility, partial indexes, JSONB, UUIDv7, order columns) | 7 (former 044–050) |
| [ADR-007](ADR-007-arvent-attributes-and-casts.md) | Arvent — Attributes, Casts & Events | 12 (former 051–062) |
| [ADR-008](ADR-008-arvent-relationships.md) | Arvent — Relationships & Polymorphism | 14 (former 063–076) |

## Runtime services

| ADR | Subject | Decisions absorbed |
|---|---|---|
| [ADR-009](ADR-009-cache-session-storage.md) | Cache, Session & Storage (Protocols, lazy imports, opt-in session middleware, HMAC URLs, versioner, path-generator DI, queue restart marker) | 7 (former 077–083) |
| [ADR-010](ADR-010-auth.md) | Authentication (password hashing, token storage, session guard, gate fail-closed, email validation, refresh tokens, ownership, email verification, repository abstraction, middleware fixes) | 10 (former 084–093) |
| [ADR-011](ADR-011-queue.md) | Queue Subsystem (job model, drivers, allowlist, worker loop, ShouldQueue, retry/DLQ, delay/priority, broker selection) | 8 (former 094–101) |
| [ADR-012](ADR-012-events-mail-notifications.md) | Events, Mail & Notifications | 3 (former 102–104) |
| [ADR-013](ADR-013-broadcasting.md) | Broadcasting (Reverb) — protocol layout, channel registry, ShouldBroadcast, single-loop broker, Pusher protocol surface, channel-auth HMAC, fake, bench gate | 8 (former 105–112) |
| [ADR-014](ADR-014-scheduling.md) | Scheduling — croniter expressions, asyncio.TaskGroup concurrency | 2 (former 113–114) |
| [ADR-015](ADR-015-i18n.md) | Internationalisation — Python translation backend, locale middleware, catalog ETag | 3 (former 115–117) |
| [ADR-016](ADR-016-observability.md) | Observability — OTel backbone, module layout, middleware placement | 3 (former 118–120) |
| [ADR-017](ADR-017-console.md) | Console / CLI — packaging, Typer promotion, framework bootstrap, command I/O, stub templates, single-binary consolidation | 6 (former 121–126) |
| [ADR-018](ADR-018-maintenance-mode-marker.md) | Maintenance mode marker design (filesystem marker at `storage/framework/down`) | 1 (former 127) |

## Companion packages

| ADR | Subject | Decisions absorbed |
|---|---|---|
| [ADR-019](ADR-019-arvel-permission.md) | `arvel-permission` — full package design (workspace member + polymorphic RBAC, standalone event system, `UnauthorizedException` typed exception, async `MorphToMany` pivot mapping) | 4 (former 128–131, merged in WI-arvel-005) |
| [ADR-020](ADR-020-arvel-image.md) | `arvel-image` — full package design (Pillow driver, medialibrary parity, runtime, SSRF guard + DNS-rebinding/MIME hardening, 1.0 public-API rename + MRO guard, MinIO test fixture, aiohttp CVE pin) | 1 (former WI-arvel-003 merge of former 132–140) |
| [ADR-023](ADR-023-arvel-audit.md) | `arvel-audit` — full package design (two layers in one package, lifecycle-hook trail, redaction/exclusion attrs, polymorphic identity, opt-in AES-GCM encryption, fluent activity recorder) | new (WI-arvel-006) |
| [ADR-024](ADR-024-arvel-oauth.md) | `arvel-oauth` — full package design (OAuth2.1 + PKCE S256, Pydantic-friendly provider classes, separate `oauth_accounts` link table, no auto-mounted routes, encrypted token storage, generic OIDC discovery) | new (WI-arvel-006) |
| [ADR-025](ADR-025-arvel-search.md) | `arvel-search` — full package design (Scout-style mixin, lifecycle-hook sync, five engines, queued sync via `SearchIndexJob`/`SearchRemoveJob`, fluent builder, `Search.fake()`, no index management) | new (WI-arvel-006) |

## Post-1.0 / parked

| ADR | Subject | Decisions absorbed |
|---|---|---|
| [ADR-021](ADR-021-config-file-settings-source.md) | Config files override env via a pydantic-settings source | 1 (former 133) |
| [ADR-022](ADR-022-public-storage-static-mount.md) | Serve `public/storage` via a scoped StaticFiles mount | 1 (former 134) |

---

Each merged ADR's `## Subsumes` block at the bottom of the file maps every absorbed decision to its `§ N` location. Old numbering history is preserved verbatim there as audit truth.
