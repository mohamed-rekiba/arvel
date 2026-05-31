# Architecture Decision Records

Chronological decisions that shaped the Arvel framework and its companion packages.
Each ADR is a permanent, append-only record. When a decision is superseded, a new ADR
documents the reversal and links to the original.

---

## Foundation

| ADR | Decision |
|-----|----------|
| [ADR-001](ADR-001-stack-selection.md) | Adopt FastAPI + Pydantic + SQLAlchemy + Alembic + Taskiq as the framework stack |
| [ADR-002](ADR-002-custom-di-container.md) | Build a custom DI container instead of adopting Dishka/Lagom/Punq |
| [ADR-003](ADR-003-monorepo-uv-workspaces.md) | Monorepo with `uv` workspaces; skeleton auto-split |
| [ADR-004](ADR-004-two-packages-extras-not-subpackages.md) | Two PyPI packages at 0.x; defer sub-splitting; optional extras for drivers |
| [ADR-005](ADR-005-mypy-pyright-parity.md) | Enforce both `mypy --strict` and `pyright --strict` — parity required |
| [ADR-018](ADR-018-canonical-app-layout.md) | Canonical application layout |
| [ADR-019](ADR-019-with-routing-loader-design.md) | `with_routing(...)` loader design |
| [ADR-051](ADR-051-enforce-quality-gates.md) | Enforce zero-warning quality gates |
| [ADR-052](ADR-052-two-checker-suppression-floor.md) | Two-checker policy and the irreducible suppression floor |

## HTTP Layer

| ADR | Decision |
|-----|----------|
| [ADR-006](ADR-006-route-facade-fastapi-wrapping.md) | Route facade wraps FastAPI APIRouter; group state in ContextVar stack |
| [ADR-007](ADR-007-resource-openapi-opt-in.md) | Resource OpenAPI schemas are opt-in via ClassVar, not AST introspection |
| [ADR-008](ADR-008-two-tier-middleware.md) | Two-tier middleware: Arvel Pipeline at route level, Starlette at app level |
| [ADR-009](ADR-009-ratelimit-store-abc.md) | Rate-limit store is an ABC with InMemory + Redis drivers, container-resolved |
| [ADR-016](ADR-016-http-database-bridge-exemption.md) | Sanctioned `http → database` exemption for `DatabaseTransaction` middleware |
| [ADR-100](ADR-100-security-headers-middleware-placement.md) | `SecurityHeadersMiddleware` — pure-ASGI, lives in `arvel.http.middleware` |
| [ADR-111](ADR-111-http-exception-handler-default.md) | `HttpExceptionHandler` as the default error handler |
| [ADR-112](ADR-112-scope-middleware-wiring.md) | `ArvelScopeMiddleware` wired into `into_asgi()` |

## Database / ORM (Arvent)

| ADR | Decision |
|-----|----------|
| [ADR-011](ADR-011-eloquent-on-sqla-mixin.md) | Eloquent layer is a mixin on SQLAlchemy, not a fork |
| [ADR-012](ADR-012-schema-dsl-compiles-to-alembic.md) | Schema DSL compiles to Alembic ops — never raw SQL |
| [ADR-013](ADR-013-kwarg-shorthand-safe-binding.md) | `where(col=value)` binds via `getattr`, never string SQL |
| [ADR-014](ADR-014-encrypted-type-aesgcm.md) | `EncryptedType`: AES-GCM with random + deterministic modes |
| [ADR-015](ADR-015-migration-reversibility.md) | Migration reversibility enforced at registration time |
| [ADR-022](ADR-022-morph-discriminator-short-class-name.md) | Morph discriminator uses short class name |
| [ADR-023](ADR-023-belongs-to-many-upsert.md) | `BelongsToMany` pivot attach: UPSERT on PK conflict |
| [ADR-041](ADR-041-has-many-method-pattern.md) | `HasMany` uses method pattern, not class-attribute descriptor |
| [ADR-042](ADR-042-recursive-cte-anchor.md) | Recursive CTE anchor derived from existing WHERE scope |
| [ADR-043](ADR-043-db-transaction-savepoints.md) | `DB.transaction()` uses `begin_nested()` for nesting |
| [ADR-044](ADR-044-query-logging-sync-engine.md) | `QueryLoggingServiceProvider` hooks sync-engine events |
| [ADR-046](ADR-046-model-metaclass-forwarding.md) | Model class-level QB forwarding via metaclass |
| [ADR-047](ADR-047-qb-write-ops-core.md) | QB write ops use SQLAlchemy Core, not ORM unit-of-work |
| [ADR-048](ADR-048-table-query-builder-separate.md) | `TableQueryBuilder` is a separate class |
| [ADR-049](ADR-049-soft-delete-global-scope.md) | Soft-delete filter as `GlobalScope` |
| [ADR-050](ADR-050-collection-list-subclass.md) | `Collection[T]` is a `list[T]` subclass |
| [ADR-071](ADR-071-migration-runner.md) | Migration runner architecture |
| [ADR-076](ADR-076-mapped-as-dataclass-on-model.md) | `Model` mixes in `MappedAsDataclass` for typed `__init__` |
| [ADR-095](ADR-095-postgresql-fts-thin-helpers.md) | PostgreSQL FTS — thin helpers over searchable mixin |
| [ADR-096](ADR-096-blueprint-partial-index-and-nulls-not-distinct.md) | Blueprint DSL exposes partial index `where=`, `unique=`, and `NULLS NOT DISTINCT` |
| [ADR-097](ADR-097-blueprint-jsonb-typedecorator.md) | `Blueprint.jsonb()` via TypeDecorator |
| [ADR-103](ADR-103-remove-basemodelmixin-sync-shadow.md) | Remove sync shadow methods from BaseModelMixin |
| [ADR-104](ADR-104-uuid7-stdlib.md) | Use `uuid.uuid7` from stdlib instead of a custom implementation |
| [ADR-113](ADR-113-order-column-select-max.md) | `order_column` assigned via `SELECT MAX + 1` |
| [ADR-118](ADR-118-framework-query-builder-fixes.md) | Framework query builder critical fixes |
| [ADR-157](ADR-157-clean-model-syntax-type-inferred-columns.md) | Clean model syntax: type-inferred columns + `field()` |

## Cache, Session, Storage

| ADR | Decision |
|-----|----------|
| [ADR-025](ADR-025-cache-session-storage-protocols.md) | Store/Driver interfaces as `typing.Protocol`, not ABC |
| [ADR-026](ADR-026-lazy-optional-dep-imports.md) | Lazy optional-dependency imports in cloud drivers |
| [ADR-027](ADR-027-session-middleware-opt-in.md) | `StartSession` middleware is opt-in, not auto-global |
| [ADR-028](ADR-028-local-driver-temp-url-hmac.md) | `LocalDriver` temporary URLs use HMAC-SHA256 + expiry |
| [ADR-073](ADR-073-queue-restart-marker.md) | Queue restart marker via cache |
| [ADR-102](ADR-102-cache-versioner-invalidation.md) | `CacheVersioner` — version-stamp invalidation without flush |
| [ADR-114](ADR-114-path-generator-di-resolution.md) | `PathGenerator` resolved via DI container with fallback |

## Auth

| ADR | Decision |
|-----|----------|
| [ADR-029](ADR-029-password-hashing-bcrypt-default.md) | Password hashing — bcrypt default, argon2id opt-in |
| [ADR-030](ADR-030-token-storage-sha256.md) | Personal access token storage — SHA-256 + Sanctum pattern |
| [ADR-031](ADR-031-session-guard-alignment.md) | `SessionGuard` alignment to Arvel `SessionData` |
| [ADR-032](ADR-032-gate-fail-closed.md) | Gate fail-closed — unregistered ability → `AuthorizationException` |
| [ADR-077](ADR-077-email-validation-at-boundary.md) | Email validation at the API boundary, not on the column |
| [ADR-078](ADR-078-refresh-token-storage-strategy.md) | Refresh-token storage strategy |
| [ADR-086](ADR-086-auth-subsystem-ownership.md) | Auth subsystem ownership: kit → framework |
| [ADR-087](ADR-087-email-verification-signed-url.md) | Email verification: signed URL over DB token |
| [ADR-088](ADR-088-refresh-token-repository-abstraction.md) | `RefreshTokenRepository` as a swappable abstraction |
| [ADR-110](ADR-110-auth-guard-password-verification.md) | Session guard must verify password before login |
| [ADR-119](ADR-119-auth-middleware-orm-completions.md) | Auth middleware and ORM correctness fixes |

## Queues

| ADR | Decision |
|-----|----------|
| [ADR-033](ADR-033-job-pydantic-basemodel.md) | `Job` is a Pydantic `BaseModel` |
| [ADR-034](ADR-034-four-queue-drivers.md) | Four backends; sync is the default |
| [ADR-035](ADR-035-job-class-allowlist.md) | Job class allowlist for deserialization safety |
| [ADR-036](ADR-036-worker-loop-design.md) | `queue:work` worker loop — asyncio + SIGTERM drain |
| [ADR-040](ADR-040-shouldqueue-bus-integration.md) | `ShouldQueue` uses `ListenerJob` bridging to Bus |
| [ADR-045](ADR-045-worker-retry-dlq.md) | Worker retry + DLQ — attempt tracking in envelope |
| [ADR-066](ADR-066-job-delay-priority-first-class.md) | Per-message delay and priority as first-class `Job` fields |
| [ADR-067](ADR-067-taskiq-broker-by-url-scheme.md) | Taskiq broker selection by URL scheme |

## Events, Mail, Notifications

| ADR | Decision |
|-----|----------|
| [ADR-037](ADR-037-event-pydantic-basemodel.md) | `Event` is a Pydantic `BaseModel` |
| [ADR-038](ADR-038-mailable-abc-design.md) | `Mailable` is an ABC, not Pydantic `BaseModel` |
| [ADR-039](ADR-039-notification-channels.md) | Notification channels — mail + database + log + broadcast stub |

## Broadcasting (Reverb)

| ADR | Decision |
|-----|----------|
| [ADR-053](ADR-053-broadcaster-protocol-layout.md) | `Broadcaster` protocol + driver layout |
| [ADR-054](ADR-054-channel-registry-pattern-matching.md) | `Broadcast.channel()` registry — exact pattern matching, no wildcards |
| [ADR-055](ADR-055-should-broadcast-mixin.md) | `ShouldBroadcast` is a mixin on `Event`, not a separate listener type |
| [ADR-056](ADR-056-reverb-single-event-loop.md) | Reverb is single-event-loop + Redis pub/sub for horizontal scale |
| [ADR-057](ADR-057-pusher-protocol-v7-surface.md) | Pusher protocol v7 — what is implemented, what is deferred |
| [ADR-058](ADR-058-channel-auth-hmac-scheme.md) | Channel-auth HMAC-SHA256 signature scheme |
| [ADR-059](ADR-059-broadcaster-fake-in-arvel-testing.md) | `BroadcasterFake` lives under `arvel.testing.broadcasting` |
| [ADR-061](ADR-061-reverb-benchmark-job-advisory.md) | Reverb benchmark CI job is advisory (`continue-on-error: true`) |
| [ADR-065](ADR-065-bench-reverb-hard-gate.md) | Promote `bench-reverb` from advisory to hard CI gate |

## Scheduling

| ADR | Decision |
|-----|----------|
| [ADR-062](ADR-062-croniter-for-schedule-expressions.md) | Use `croniter` for scheduler expression parsing |
| [ADR-064](ADR-064-asyncio-taskgroup-for-scheduler-concurrency.md) | Use `asyncio.TaskGroup` for scheduler concurrency |

## Console / CLI

| ADR | Decision |
|-----|----------|
| [ADR-020](ADR-020-cli-packaging.md) | `arvel-cli` packaging strategy |
| [ADR-024](ADR-024-typer-single-command-promotion.md) | Typer single-command promotion workaround |
| [ADR-068](ADR-068-cli-framework-bootstrap.md) | CLI optionally bootstraps a framework Application via `bootstrap/app.py` |
| [ADR-069](ADR-069-arvel-script-collision.md) | Resolve the `arvel` console-script collision: rename to `arvel-new` |
| [ADR-070](ADR-070-command-io-surface-mvp.md) | `Command` I/O surface: ship the minimum-viable subset, defer prompts and tables |
| [ADR-074](ADR-074-make-stub-templates.md) | Stub-template ownership in `make:*` commands |
| [ADR-075](ADR-075-single-arvel-binary-consolidation.md) | Consolidate the CLI into a single `arvel` binary — delete `arvel-cli` |

## i18n

| ADR | Decision |
|-----|----------|
| [ADR-063](ADR-063-python-files-as-translation-backend.md) | Use Python files as the default translation backend |
| [ADR-092](ADR-092-set-locale-middleware-placement.md) | `SetLocaleMiddleware` placement in `arvel.i18n.middleware` |
| [ADR-101](ADR-101-catalog-controller-etag-lock.md) | `CatalogController` — ETag + per-locale lock |

## Observability

| ADR | Decision |
|-----|----------|
| [ADR-089](ADR-089-otel-as-observability-backbone.md) | OTel SDK as the observability backbone |
| [ADR-090](ADR-090-observability-module-layout.md) | `arvel/observability/` as the module home |
| [ADR-091](ADR-091-observability-middleware-placement.md) | `ObservabilityMiddleware` placement: outermost, before auth |

## Maintenance

| ADR | Decision |
|-----|----------|
| [ADR-072](ADR-072-maintenance-mode-marker.md) | Maintenance mode marker design |

## Testing

| ADR | Decision |
|-----|----------|
| [ADR-017](ADR-017-per-module-coverage-gates.md) | Per-module coverage gates |
| [ADR-093](ADR-093-create-test-app-context-manager.md) | `create_test_app()` as async context manager |

## arvel-permission

| ADR | Decision |
|-----|----------|
| [ADR-079](ADR-079-arvel-permission-spatie-parity.md) | `arvel-permission` — Spatie Permission parity |
| [ADR-094](ADR-094-permission-integer-pk-support.md) | Integer PK support strategy (superseded by ADR-122) |
| [ADR-098](ADR-098-has-level-on-has-roles.md) | Role hierarchy — numeric level rejected; use role names |
| [ADR-105](ADR-105-remove-has-roles-mixin.md) | Remove legacy `HasRolesMixin` in favour of `HasRoles`/`HasPermissions` |
| [ADR-107](ADR-107-permission-pivot-composite-pk.md) | Permission pivot tables: composite primary key |
| [ADR-120](ADR-120-arvel-permission-events-standalone.md) | Standalone event system (no framework event bus dependency) |
| [ADR-121](ADR-121-arvel-permission-exception-hierarchy.md) | `UnauthorizedException` as a typed exception hierarchy |
| [ADR-122](ADR-122-async-morph-to-many-permission.md) | Async `MorphToMany` for permission pivots (supersedes ADR-094) |

## arvel-image

| ADR | Decision |
|-----|----------|
| [ADR-080](ADR-080-arvel-image-pillow-only.md) | Pillow-only driver — no wand/libvips dependency |
| [ADR-081](ADR-081-arvel-image-medialibrary-scope.md) | Scope: ship laravel-medialibrary parity |
| [ADR-082](ADR-082-arvel-image-medialibrary-runtime.md) | Runtime layer: synchronous conversions + short-class polymorphism |
| [ADR-099](ADR-099-has-media-aliases-and-mixin-export.md) | `HasMedia` aliases and `HasMediaMixin` re-export |
| [ADR-108](ADR-108-model-id-varchar.md) | Change `media.model_id` from INTEGER to VARCHAR(36) |
| [ADR-109](ADR-109-ssrf-guard-ipaddress.md) | SSRF guard via stdlib `ipaddress` |
