# Architecture Decision Records

Decisions that shaped the Arvel framework and its companion packages, grouped by subsystem. Numbers are contiguous and topic-ordered; superseded and follow-up decisions have been folded into their canonical records.

Last reconciled: 2026-06-05. The most recent reconciliation pass (WI-arvel-003) merged the seven `arvel-image` ADRs (former 132, 133, 134, 135, 138, 139, 140) into a single ADR-132 and compact-renumbered the two framework ADRs that landed right after (former 136 → 133, former 137 → 134). Next free ADR number is **135**.

## Foundation & Project

| ADR | Decision |
|-----|----------|
| [ADR-001](ADR-001-stack-selection.md) | Adopt FastAPI + Pydantic + SQLAlchemy + Alembic + Taskiq as the framework stack |
| [ADR-002](ADR-002-custom-di-container.md) | Build a custom DI container instead of adopting Dishka/Lagom/Punq |
| [ADR-003](ADR-003-monorepo-uv-workspaces.md) | Monorepo with `uv` workspaces |
| [ADR-004](ADR-004-two-packages-extras-not-subpackages.md) | Single `arvel` package with optional extras; companions as separate distributions |
| [ADR-005](ADR-005-canonical-app-layout.md) | Canonical application layout |
| [ADR-006](ADR-006-with-routing-loader-design.md) | `with_routing(...)` loader design |
| [ADR-007](ADR-007-mkdocs-material-now.md) | Adopt mkdocs-material now; auto-generate API reference from docstrings |

## Quality & Testing

| ADR | Decision |
|-----|----------|
| [ADR-008](ADR-008-mypy-pyright-parity.md) | Enforce both `mypy --strict` and `pyright --strict` (parity required) |
| [ADR-009](ADR-009-enforce-quality-gates.md) | Enforce Zero-Warning Quality Gates |
| [ADR-010](ADR-010-two-checker-suppression-floor.md) | Two-Checker Policy and the Irreducible Suppression Floor |
| [ADR-011](ADR-011-per-module-coverage-gates.md) | Per-module coverage gates (promoted from FB-010) |
| [ADR-012](ADR-012-create-test-app-context-manager.md) | create_test_app() as async context manager |

## HTTP Layer

| ADR | Decision |
|-----|----------|
| [ADR-013](ADR-013-route-facade-fastapi-wrapping.md) | Route facade wraps FastAPI APIRouter, group state in a ContextVar stack |
| [ADR-014](ADR-014-resource-openapi-opt-in.md) | Resource OpenAPI schemas are opt-in via ClassVar, not AST introspection |
| [ADR-015](ADR-015-two-tier-middleware.md) | Two-tier middleware: Arvel Pipeline at route level, Starlette middleware at app level |
| [ADR-016](ADR-016-ratelimit-store-abc.md) | Rate-limit store is a Protocol with InMemory + Redis drivers, container-resolved |
| [ADR-017](ADR-017-http-database-bridge-exemption.md) | Sanctioned http→database exemption for `DatabaseTransaction` middleware |
| [ADR-018](ADR-018-security-headers-middleware-placement.md) | `SecurityHeadersMiddleware` — pure-ASGI, in `arvel.http.middleware` |
| [ADR-019](ADR-019-http-exception-handler-default.md) | HttpExceptionHandler as Default Error Handler |
| [ADR-020](ADR-020-scope-middleware-wiring.md) | ArvelScopeMiddleware Wired in into_asgi() |

## Database / ORM (Arvent)

| ADR | Decision |
|-----|----------|
| [ADR-021](ADR-021-arvent-on-sqla-mixin.md) | Arvent is a mixin on SQLAlchemy, not a fork |
| [ADR-022](ADR-022-mapped-as-dataclass-on-model.md) | `Model` mixes in `MappedAsDataclass` for typed `__init__` |
| [ADR-023](ADR-023-clean-model-syntax-type-inferred-columns.md) | Clean model syntax: type-inferred columns + `field()` |
| [ADR-024](ADR-024-model-metaclass-forwarding.md) | Model Class-Level QB Forwarding via Metaclass |
| [ADR-025](ADR-025-qb-write-ops-core.md) | QB Write Ops Use SQLAlchemy Core, Not ORM Unit-of-Work |
| [ADR-026](ADR-026-table-query-builder-separate.md) | TableQueryBuilder Is a Separate Class |
| [ADR-027](ADR-027-collection-list-subclass.md) | Collection[T] Is a list[T] Subclass |
| [ADR-028](ADR-028-model-collection.md) | ModelCollection for Arvent model result sets |
| [ADR-029](ADR-029-kwarg-shorthand-safe-binding.md) | Kwarg-shorthand `where(col=value)` binds parameters via `getattr`, never string SQL |
| [ADR-030](ADR-030-where-predicate-engine.md) | WHERE Predicate Engine and Clause Polish |
| [ADR-031](ADR-031-qb-conditional-groups-and-efficient-exists.md) | Query Builder Conditional Groups, `unless`/`tap`, and Efficient `exists` |
| [ADR-032](ADR-032-write-path-completeness.md) | Write-path completeness (insert_or_ignore / upsert count / truncate / insert_using / increment_each) |
| [ADR-033](ADR-033-subquery-from-join-select.md) | Subquery FROM / JOIN / SELECT |
| [ADR-034](ADR-034-framework-query-builder-fixes.md) | Framework Query Builder Critical Fixes |
| [ADR-035](ADR-035-streaming-chunking-completeness.md) | Streaming and Chunking Completeness |
| [ADR-036](ADR-036-pagination-http-json-parity.md) | Pagination HTTP + JSON parity |
| [ADR-037](ADR-037-debugging-query-log.md) | Debugging and query-log parity |
| [ADR-038](ADR-038-date-like-join-helpers.md) | Date/time, LIKE, and join helpers |
| [ADR-039](ADR-039-postgresql-fts-thin-helpers.md) | PostgreSQL FTS — Thin Helpers Over Searchable Mixin |
| [ADR-040](ADR-040-transaction-retry.md) | Closure-form Transaction Retry on Deadlock |
| [ADR-041](ADR-041-db-transaction-savepoints.md) | DB.transaction() uses begin_nested() for nesting |
| [ADR-042](ADR-042-query-logging-sync-engine.md) | QueryLoggingServiceProvider hooks sync_engine events |
| [ADR-043](ADR-043-recursive-cte-anchor.md) | Recursive CTE anchor derived from existing WHERE scope |
| [ADR-044](ADR-044-schema-dsl-compiles-to-alembic.md) | Schema DSL compiles to Alembic ops (never raw SQL) |
| [ADR-045](ADR-045-migration-runner.md) | Migration runner architecture |
| [ADR-046](ADR-046-migration-reversibility.md) | Migration reversibility enforced at registration time |
| [ADR-047](ADR-047-blueprint-partial-index-and-nulls-not-distinct.md) | Blueprint DSL — Expose Partial Index `where=`, `unique=`, and `NULLS NOT DISTINCT` |
| [ADR-048](ADR-048-blueprint-jsonb-typedecorator.md) | `Blueprint.jsonb()` via TypeDecorator |
| [ADR-049](ADR-049-uuid7-stdlib.md) | Use uuid.uuid7 from stdlib Instead of Custom Implementation |
| [ADR-050](ADR-050-order-column-select-max.md) | order_column assigned via SELECT MAX + 1 |

## ORM — Attributes, Casts & Events

| ADR | Decision |
|-----|----------|
| [ADR-051](ADR-051-unified-attribute-descriptor.md) | Unified `Attribute` descriptor |
| [ADR-052](ADR-052-attribute-cast-protocol.md) | Attribute-level Custom Cast Protocol |
| [ADR-053](ADR-053-cast-aware-dirty-tracking.md) | Cast-aware Dirty Tracking |
| [ADR-054](ADR-054-enum-extended-casts.md) | Enum and extended built-in casts |
| [ADR-055](ADR-055-declarative-encrypted-casts.md) | Declarative encrypted casts + app `Encrypter` |
| [ADR-056](ADR-056-encrypted-type-aesgcm.md) | EncryptedType: AES-GCM with random + deterministic modes |
| [ADR-057](ADR-057-hashed-cast-and-mass-assignment-bypass.md) | `hashed` Cast and Explicit Mass-Assignment Bypass |
| [ADR-058](ADR-058-event-suppression-and-quiet-persistence.md) | Re-entrant Event Suppression and Quiet Persistence |
| [ADR-059](ADR-059-static-event-registration.md) | Static event registration + custom event objects |
| [ADR-060](ADR-060-timestamp-controls.md) | Timestamp controls |
| [ADR-061](ADR-061-distinct-delete-replicate-events.md) | Distinct soft/hard-delete and replicate events |
| [ADR-062](ADR-062-factory-enhancements.md) | Factory enhancements |

## ORM — Relationships & Polymorphism

| ADR | Decision |
|-----|----------|
| [ADR-063](ADR-063-has-many-method-pattern.md) | HasMany uses method pattern, not class-attribute descriptor |
| [ADR-064](ADR-064-belongs-to-many-upsert.md) | BelongsToMany Pivot Attach: UPSERT on PK Conflict |
| [ADR-065](ADR-065-soft-delete-global-scope.md) | Soft-Delete Filter as GlobalScope |
| [ADR-066](ADR-066-morph-map-foundation.md) | Morph map foundation |
| [ADR-067](ADR-067-morph-to-inverse-relation.md) | MorphTo inverse relation |
| [ADR-068](ADR-068-morph-child-query-eager.md) | MorphOne/MorphMany query + eager integration |
| [ADR-069](ADR-069-morphed-by-many.md) | morphedByMany — inverse polymorphic many-to-many |
| [ADR-070](ADR-070-has-one-of-many.md) | has-one-of-many (latest/oldest/of_many) |
| [ADR-071](ADR-071-chaperone.md) | chaperone (inverse parent hydration) |
| [ADR-072](ADR-072-polymorphic-existence-queries.md) | polymorphic existence queries (where_has_morph / has_morph) |
| [ADR-073](ADR-073-relation-querying-completeness.md) | relation-querying completeness |
| [ADR-074](ADR-074-relationship-aggregate-completeness.md) | relationship aggregate completeness |
| [ADR-075](ADR-075-pivot-ergonomics.md) | pivot ergonomics for BelongsToMany |
| [ADR-076](ADR-076-relation-defaults-eager-control.md) | relation defaults, eager control, and cascade save |

## Cache, Session, Storage

| ADR | Decision |
|-----|----------|
| [ADR-077](ADR-077-cache-session-storage-protocols.md) | Store/Driver interfaces as `typing.Protocol`, not ABC |
| [ADR-078](ADR-078-lazy-optional-dep-imports.md) | Lazy optional-dependency imports in cloud drivers |
| [ADR-079](ADR-079-session-middleware-opt-in.md) | StartSession middleware is opt-in, not auto-global |
| [ADR-080](ADR-080-local-driver-temp-url-hmac.md) | LocalDriver temporary URLs use HMAC-SHA256 + expiry |
| [ADR-081](ADR-081-cache-versioner-invalidation.md) | `CacheVersioner` — Version-stamp invalidation without flush |
| [ADR-082](ADR-082-path-generator-di-resolution.md) | PathGenerator resolved via DI container with fallback |
| [ADR-083](ADR-083-queue-restart-marker.md) | Queue restart marker via cache |

## Auth

| ADR | Decision |
|-----|----------|
| [ADR-084](ADR-084-password-hashing-bcrypt-default.md) | Password Hashing — bcrypt default, argon2id opt-in |
| [ADR-085](ADR-085-token-storage-sha256.md) | Personal Access Token Storage — SHA-256 + Sanctum Pattern |
| [ADR-086](ADR-086-session-guard-alignment.md) | SessionGuard Alignment to Arvel SessionData |
| [ADR-087](ADR-087-gate-fail-closed.md) | Gate Fail-Closed — Unregistered Ability → AuthorizationException |
| [ADR-088](ADR-088-email-validation-at-boundary.md) | Email validation at the API boundary, not on the column |
| [ADR-089](ADR-089-refresh-token-storage-strategy.md) | Refresh-token storage strategy |
| [ADR-090](ADR-090-auth-subsystem-ownership.md) | Auth subsystem ownership: kit → framework |
| [ADR-091](ADR-091-email-verification-signed-url.md) | Email verification: signed URL over DB token |
| [ADR-092](ADR-092-refresh-token-repository-abstraction.md) | `RefreshTokenRepository` as a swappable abstraction |
| [ADR-093](ADR-093-auth-middleware-orm-completions.md) | Auth Middleware and ORM Correctness Fixes |

## Queues

| ADR | Decision |
|-----|----------|
| [ADR-094](ADR-094-job-pydantic-basemodel.md) | Job model — Pydantic BaseModel as the job primitive |
| [ADR-095](ADR-095-four-queue-drivers.md) | Driver selection — four backends with sync as default |
| [ADR-096](ADR-096-job-class-allowlist.md) | Job class allowlist for deserialization safety |
| [ADR-097](ADR-097-worker-loop-design.md) | queue:work worker loop design (asyncio + SIGTERM drain) |
| [ADR-098](ADR-098-shouldqueue-bus-integration.md) | ShouldQueue Uses ListenerJob Bridging to Bus |
| [ADR-099](ADR-099-worker-retry-dlq.md) | Worker Retry + DLQ — Attempt Tracking in Envelope |
| [ADR-100](ADR-100-job-delay-priority-first-class.md) | Per-message delay and priority as first-class `Job` fields |
| [ADR-101](ADR-101-taskiq-broker-by-url-scheme.md) | Taskiq broker selection by URL scheme; queue-name suffix for Redis-broker priority |

## Events, Mail, Notifications

| ADR | Decision |
|-----|----------|
| [ADR-102](ADR-102-event-pydantic-basemodel.md) | Event is a Pydantic BaseModel |
| [ADR-103](ADR-103-mailable-abc-design.md) | Mailable is an ABC (not Pydantic BaseModel) |
| [ADR-104](ADR-104-notification-channels.md) | Notification Channels — mail + database + log + broadcast stub |

## Broadcasting (Reverb)

| ADR | Decision |
|-----|----------|
| [ADR-105](ADR-105-broadcaster-protocol-layout.md) | `Broadcaster` Protocol + Driver Layout |
| [ADR-106](ADR-106-channel-registry-pattern-matching.md) | `Broadcast.channel()` Registry — Exact Pattern Matching, No Wildcards |
| [ADR-107](ADR-107-should-broadcast-mixin.md) | `ShouldBroadcast` is a Mixin on `Event`, Not a Separate Listener Type |
| [ADR-108](ADR-108-reverb-single-event-loop.md) | Reverb is Single-Event-Loop + Redis Pub/Sub Horizontal Scale |
| [ADR-109](ADR-109-pusher-protocol-v7-surface.md) | Pusher Protocol v7 — What We Implement, What We Don't |
| [ADR-110](ADR-110-channel-auth-hmac-scheme.md) | Channel-Auth HMAC-SHA256 Signature Scheme |
| [ADR-111](ADR-111-broadcaster-fake-in-arvel-testing.md) | `BroadcasterFake` Lives Under `arvel.testing.broadcasting` |
| [ADR-112](ADR-112-bench-reverb-hard-gate.md) | Promote `bench-reverb` from advisory to hard CI gate |

## Scheduling

| ADR | Decision |
|-----|----------|
| [ADR-113](ADR-113-croniter-for-schedule-expressions.md) | Use `croniter` for scheduler expression parsing |
| [ADR-114](ADR-114-asyncio-taskgroup-for-scheduler-concurrency.md) | Use `asyncio.TaskGroup` for scheduler concurrency |

## i18n

| ADR | Decision |
|-----|----------|
| [ADR-115](ADR-115-python-files-as-translation-backend.md) | Use Python files as the default translation backend |
| [ADR-116](ADR-116-set-locale-middleware-placement.md) | SetLocaleMiddleware placement in arvel.i18n.middleware |
| [ADR-117](ADR-117-catalog-controller-etag-lock.md) | `CatalogController` — ETag + per-locale lock |

## Observability

| ADR | Decision |
|-----|----------|
| [ADR-118](ADR-118-otel-as-observability-backbone.md) | OTel SDK as the Observability Backbone |
| [ADR-119](ADR-119-observability-module-layout.md) | `arvel/observability/` as the Module Home |
| [ADR-120](ADR-120-observability-middleware-placement.md) | ObservabilityMiddleware Placement (Outermost, Before Auth) |

## Console / CLI

| ADR | Decision |
|-----|----------|
| [ADR-121](ADR-121-cli-packaging.md) | `arvel-cli` packaging strategy |
| [ADR-122](ADR-122-typer-single-command-promotion.md) | Typer Single-Command Promotion Workaround |
| [ADR-123](ADR-123-cli-framework-bootstrap.md) | CLI optionally bootstraps a framework Application via `bootstrap/app.py` |
| [ADR-124](ADR-124-command-io-surface-mvp.md) | `Command` / `Context` I/O surface: ship the minimum-viable subset, defer prompts and tables |
| [ADR-125](ADR-125-make-stub-templates.md) | Stub-template ownership in `make:*` commands |
| [ADR-126](ADR-126-single-arvel-binary-consolidation.md) | Consolidate the CLI into a single `arvel` binary (delete `arvel-cli`) |

## Maintenance

| ADR | Decision |
|-----|----------|
| [ADR-127](ADR-127-maintenance-mode-marker.md) | Maintenance mode marker design |

## arvel-permission

| ADR | Decision |
|-----|----------|
| [ADR-128](ADR-128-arvel-permission-package.md) | `arvel-permission` package: workspace member, polymorphic RBAC |
| [ADR-129](ADR-129-arvel-permission-events-standalone.md) | arvel-permission: Standalone event system |
| [ADR-130](ADR-130-arvel-permission-exception-hierarchy.md) | arvel-permission: UnauthorizedException as a typed exception |
| [ADR-131](ADR-131-async-morph-to-many-permission.md) | Async MorphToMany for arvel-permission pivots |

## arvel-image

| ADR | Decision |
|-----|----------|
| [ADR-132](ADR-132-arvel-image.md) | `arvel-image` — full package design (Pillow driver, medialibrary parity, runtime, SSRF guard + DNS-rebinding/MIME hardening, 1.0 public-API rename + MRO guard, MinIO test fixture, aiohttp CVE pin) |

The single ADR-132 file consolidates the seven decisions that previously lived as ADR-132 / 133 / 134 / 135 / 138 / 139 / 140; see its `## Subsumes` block for the original-to-section mapping. The companion [SAD-004](../architecture/SAD-004-arvel-image.md) folds in the polish-pass SAD (former SAD-004) and the post-1.0 hardening SAD (former SAD-005).

## Config (post-1.0)

| ADR | Decision |
|-----|----------|
| [ADR-133](ADR-133-config-file-settings-source.md) | Config files override env via a pydantic-settings source (renumbered from ADR-136 in WI-arvel-003) |

## Storage extras (post-1.0)

| ADR | Decision |
|-----|----------|
| [ADR-134](ADR-134-public-storage-static-mount.md) | Serve `public/storage` via a scoped StaticFiles mount (renumbered from ADR-137 in WI-arvel-003) |
