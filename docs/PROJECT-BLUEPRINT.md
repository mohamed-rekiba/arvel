# Arvel — Project Blueprint

> **Version**: 0.1.6 | **Python**: 3.14+ | **License**: MIT | **Status**: Alpha
>
> Async-first, type-safe Python web framework inspired by Laravel. Built on FastAPI, SQLAlchemy 2.0, Pydantic, structlog, and Typer.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Module Inventory](#module-inventory)
3. [Data Model & ORM](#data-model--orm)
4. [Foundation & DI Container](#foundation--di-container)
5. [HTTP Layer](#http-layer)
6. [Authentication & Security](#authentication--security)
7. [Infrastructure Drivers](#infrastructure-drivers)
8. [CLI](#cli)
9. [Testing Architecture](#testing-architecture)
10. [Build & Tooling](#build--tooling)
11. [Documentation Site](#documentation-site)
12. [Design Patterns](#design-patterns)
13. [Type Safety Strategy](#type-safety-strategy)
14. [Code Quality Metrics](#code-quality-metrics)
15. [Review Findings Summary](#review-findings-summary)

---

## Architecture Overview

Arvel is a **layered framework library** (not a monolithic app) organized as a modular monolith with clear separation of concerns:

```
┌────────────────────────────────────────────────────┐
│                    CLI (Typer)                      │
│   arvel new | serve | db | make | queue | health   │
├────────────────────────────────────────────────────┤
│                 HTTP Layer (FastAPI)                │
│   Router · Kernel · Middleware · Controller         │
│   Resources · Exception Handler · URL Generator    │
├────────────────────────────────────────────────────┤
│              Business Logic Layer                   │
│  Validation · Events · Notifications · Mail        │
│  Queue · Scheduler · Broadcasting · Search         │
├────────────────────────────────────────────────────┤
│               Data Layer (SQLAlchemy)               │
│  ArvelModel · Repository · QueryBuilder            │
│  Observers · Migrations · Relationships · Scopes   │
├────────────────────────────────────────────────────┤
│             Foundation Layer                        │
│  Application · Container (DI) · ServiceProvider    │
│  Pipeline · Config (Pydantic Settings)             │
├────────────────────────────────────────────────────┤
│             Cross-Cutting Concerns                 │
│  Auth (JWT/OAuth) · Security (Encryption/Hashing)  │
│  Observability (structlog/OTEL/Sentry) · Cache     │
│  Storage (Local/S3) · Locks · I18n · Sessions      │
└────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| ASGI framework | FastAPI + Starlette | OpenAPI generation, async-native, Pydantic integration |
| ORM | SQLAlchemy 2.0 async | `Mapped[T]` type safety, mature ecosystem, Alembic migrations |
| Validation & config | Pydantic everywhere | End-to-end type language — requests, settings, serialization |
| DI | Custom container | Scoped (app/request/session), constructor injection, `Annotated` support |
| Logging | structlog | Structured JSON logging, async-safe, context propagation |
| CLI | Typer | Click-based, type-driven, auto-help, subcommand architecture |
| Auth | PyJWT + bcrypt | HS256 by default, OIDC/OAuth2 support, guard-based architecture |

---

## Module Inventory

### Source Files: 281 Python files in `src/arvel/`

| Module | Files | Key Types | Responsibility |
|--------|-------|-----------|----------------|
| `data/` | 26 | `ArvelModel`, `Repository[T]`, `QueryBuilder[T]`, `Transaction`, `ModelObserver[T]`, `ObserverRegistry`, `MigrationRunner` | ORM, repositories, query builder, relationships, migrations, scopes, soft deletes, collections, pagination |
| `http/` | 20 | `Router`, `HttpKernel`, `BaseController`, `MiddlewareStack`, `ResourceResponse` | HTTP routing, middleware, controllers, resources, exception handling, URL generation |
| `cli/` | 20 | `new_app`, `db_app`, `serve_app`, `make_app` | Typer CLI commands, Jinja2 code generation templates |
| `auth/` | 18 | `JwtGuard`, `AuthManager`, `TokenService`, `OAuthProviderRegistry`, `AuthContext` | JWT/OAuth/OIDC authentication, guards, policies, tokens, audit |
| `queue/` | 19 | `Job`, `QueueManager`, `Chain`, `Batch` | Background jobs, sync/taskiq drivers, batching, chaining, failed job handling |
| `search/` | 15 | `Searchable`, `SearchManager`, `SearchBuilder` | Full-text search: Meilisearch, Elasticsearch, collection, database drivers |
| `media/` | 14 | `MediaLibrary`, `InteractsWithMedia` | Image/file pipeline, models, mixins, conversions |
| `broadcasting/` | 14 | `BroadcastManager`, `Channel`, `PresenceChannel` | Real-time: memory, Redis, log, null drivers |
| `notifications/` | 12 | `NotificationDispatcher`, channels (mail/slack/database) | Multi-channel notifications |
| `observability/` | 11 | `configure_logging`, `HealthResult`, tracing, Sentry | structlog setup, health checks, OTEL, Sentry, request ID, access log |
| `mail/` | 9 | `MailContract`, `Mailable`, `SmtpDriver` | SMTP, log, null drivers |
| `security/` | 9 | `HashManager`, `AesEncrypter`, `RateLimitMiddleware` | Bcrypt/Argon2 hashing, AES-256-CBC encryption, CSRF, rate limiting |
| `storage/` | 9 | `StorageContract`, `LocalDriver`, `S3Driver` | File storage abstraction (local, S3, managed S3) |
| `foundation/` | 7 | `Application`, `Container`, `ServiceProvider`, `Pipeline` | Kernel, DI, config, pipeline, providers |
| `events/` | 8 | `EventDispatcher`, `Event`, `Listener` | Domain event dispatch with priority |
| `cache/` | 8 | `CacheContract`, memory/redis/null drivers | Key-value caching with TTL |
| `lock/` | 8 | `LockContract`, memory/redis/null drivers | Distributed locks |
| `validation/` | 8 | `Validator`, `FormRequest`, conditional/database rules | Input validation with Pydantic-compatible rules |
| `context/` | 6 | `Context`, `ContextMiddleware` | Request context store, deferred callbacks |
| `testing/` | 6 | `TestClient`, `ModelFactory`, fakes | Test utilities, factory pattern, infrastructure fakes |
| `scheduler/` | 6 | `Scheduler`, `ScheduleEntry` | Cron-based task scheduling |
| `logging/` | 5 | `Log` facade | Structured logging API |
| `audit/` | 5 | `AuditService`, `AuditEntry` | Audit trail for model changes |
| `activity/` | 4 | `ActivityRecorder`, `ActivityEntry` | Activity logging for models |
| `support/` | 3 | `data_get`, `type_guards` | Utility functions |
| `i18n/` | 3 | `Translator`, middleware | Internationalization |
| `session/` | 2 | `SessionSettings` | Session configuration |
| `contracts/` | 1 | Re-exports | `CacheContract`, `LockContract`, `MailContract`, `MediaContract`, `NotificationContract`, `StorageContract` |
| `infra/` | 1 | `InfrastructureProvider` | Provider for external service registration |

---

## Data Model & ORM

### ArvelModel (Active Record + Repository)

The ORM provides two complementary patterns:

**Active Record** — class methods on the model:
```python
from arvel.data import ArvelModel, Mapped, mapped_column, String, has_many

class User(ArvelModel):
    __tablename__ = "users"
    __fillable__ = {"name", "email", "bio"}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    posts: list[Post] = has_many(Post, back_populates="author")
```

**Repository** — encapsulates session access:
```python
from arvel.data import Repository

class UserRepository(Repository[User]):
    async def find_active(self) -> list[User]:
        return await self.query().where(User.is_active == True).all()
```

### QueryBuilder

Fluent, type-safe query construction with parameterized SQL:

- `where(*criteria)` — type-safe SA column expressions
- `with_("posts", "posts.comments")` — explicit eager loading (selectinload)
- `has("posts")`, `doesnt_have("posts")` — relationship existence filtering
- `where_has("posts", lambda Post: Post.is_published == True)` — relationship condition filtering
- `with_count("posts")` — correlated COUNT subqueries → `WithCount[T]` result
- `paginate(page, per_page)` — offset or cursor-based pagination
- Recursive CTE support via `RecursiveQueryBuilder`

### Relationships

| Helper | FK Location | Convention |
|--------|-------------|------------|
| `has_one(Profile)` | Profile's table | `{owner_singular}_id` |
| `has_many(Post)` | Post's table | `{owner_singular}_id` |
| `belongs_to(User)` | This model's table | `{related_singular}_id` |
| `belongs_to_many(Role)` | Pivot table | `{singular_a}_{singular_b}` alphabetical |
| `morph_to()` / `morph_many()` | Polymorphic columns | `{name}_type`, `{name}_id` |

### Transaction & Observer Lifecycle

```python
async with Transaction(session=session, observer_registry=registry) as tx:
    user = await tx.users.create({"name": "Alice", "email": "alice@test.com"})
    # Observer events: creating → created
    async with tx.nested():
        await tx.posts.create({"title": "Hello", "user_id": user.id})
```

Observer lifecycle events: `saving` → `creating`/`updating`/`deleting` → `created`/`updated`/`deleted` → `saved`

Pre-events (`creating`, `updating`, `deleting`) can return `False` to abort the operation.

### Migrations

Alembic-integrated via `MigrationRunner`. Framework packages register migrations via side-effect imports (e.g., `auth/migration.py`). CLI: `arvel db migrate`, `arvel db fresh`, `arvel db seed`.

---

## Foundation & DI Container

### Application Lifecycle

```
Application.configure(settings)
    → Provider.register(container_builder)  [for each provider]
    → Container.build()
    → Provider.boot(app)                    [for each provider]
    → FastAPI app ready (lazy on first ASGI event)
```

### Container

Scoped DI with three levels:

| Scope | Lifetime | Example |
|-------|----------|---------|
| `APP` | Application lifetime | Database engine, config |
| `REQUEST` | HTTP request | Session, auth context |
| `SESSION` | Explicit scope | Background job context |

Supports:
- `provide(interface, concrete)` — singleton per scope
- `factory(interface, factory_fn)` — fresh instance per resolution
- `value(interface, instance)` — pre-built value
- `Annotated[T, ...]` unwrapping for FastAPI compatibility
- Constructor injection via `inspect.signature`

### Pipeline

Laravel-style onion pipeline for middleware and workflows:

```python
result = await Pipeline(container).send(request).through([
    CorsMiddleware,
    AuthMiddleware,
    RateLimitMiddleware,
]).then(handler)
```

### Config

Layered Pydantic Settings: `.env` → environment variables → `config/*.py` overrides → framework defaults. Module settings discovered via `env_prefix`. Optional config caching.

---

## HTTP Layer

### Router

Extends FastAPI `APIRouter` with:
- Named routes (`name="user.show"`)
- Route groups with shared prefix/middleware
- Resource routes (`router.resource("/users", UserController)`)
- Controller discovery from class methods
- Duplicate route detection
- URL generation (`url_for("user.show", id=1)`)

### Middleware

Pure ASGI (no `BaseHTTPMiddleware`). Features:
- `MiddlewareStack` with alias/group resolution and cycle detection
- `RequestScopeMiddleware` — per-request DI container
- Rate limiting, CORS, CSRF, maintenance mode, request ID
- Terminable middleware protocol for post-response cleanup

### Controller

```python
class UserController(BaseController):
    @route("/{user_id}", methods=["GET"])
    async def show(self, user_id: int, service: Annotated[UserService, Inject]) -> User:
        return await service.find(user_id)
```

`Inject` bridges FastAPI `Depends` to the container's `resolve()`.

---

## Authentication & Security

### Auth Architecture

Guard-based authentication:
- `JwtGuard` — Bearer token validation via `TokenService`
- `AuthManager` — multi-guard orchestration
- `AuthContext` — carries `sub`, `roles`, `groups`, `claims`
- OAuth2/OIDC via `OAuthProviderRegistry` with built-in Apple/GitHub/Google/Microsoft/Facebook configs

### TokenService

HS256 JWT with required claims (`exp`, `iss`, `aud`, `sub`, `type`). Access + refresh token pairs.

### Security Module

| Feature | Implementation |
|---------|---------------|
| Password hashing | bcrypt (default), Argon2 (optional) via `HashManager` |
| Encryption | AES-256-CBC + HMAC-SHA256 (cryptography fast path, pure-Python fallback) |
| Rate limiting | Sliding window, in-memory store, ASGI middleware, `X-RateLimit-*` headers |
| CSRF | Token-based middleware |

---

## Infrastructure Drivers

All infrastructure uses the **contract/driver pattern**: an ABC defines the interface, multiple drivers implement it.

| Contract | Drivers | Config |
|----------|---------|--------|
| `CacheContract` | Memory, Redis, Null | `CacheSettings` |
| `LockContract` | Memory, Redis, Null | `LockSettings` |
| `MailContract` | SMTP, Log, Null | `MailSettings` |
| `StorageContract` | Local, S3, Managed S3 | `StorageSettings` |
| `QueueContract` | Sync, TaskIQ, Null | `QueueSettings` |
| Search | Meilisearch, Elasticsearch, Collection, Database | `SearchSettings` |
| Broadcasting | Memory, Redis, Log, Null | `BroadcastSettings` |

Each driver is an optional dependency — install via extras (`arvel[redis]`, `arvel[smtp]`, etc.).

---

## CLI

Typer-based with subcommand groups:

| Command | Purpose |
|---------|---------|
| `arvel new <name>` | Scaffold project (interactive or preset-based) |
| `arvel serve` | Dev server with hot reload |
| `arvel make model/controller/...` | Code generation via Jinja2 templates |
| `arvel db migrate/seed/fresh/status` | Database management |
| `arvel queue work` | Background worker |
| `arvel schedule run` | Cron scheduler |
| `arvel route list` | Route table |
| `arvel tinker` | IPython REPL |
| `arvel health` | Subsystem health checks |

Plugin discovery: `app/Console/Commands/*.py` auto-registers exported `typer.Typer` apps.

---

## Testing Architecture

### Strategy

- **2,877 tests**, **81% coverage**, 28.5s runtime
- **Real SQLite** for data tests (no mocking framework internals)
- **Fakes** for unit tests (`CacheFake`, `MailFake`, `QueueFake`, `StorageFake`)
- **Contract tests** for infrastructure drivers
- **Transaction rollback isolation** — connection-level transaction with rollback per test

### Fixtures

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `clean_env` | function | Strips env vars, sets test paths |
| `db_session` | function | SQLite + connection transaction + rollback |
| `transaction` | function | `Transaction` with repos + observers |
| `tmp_project` | function | Scaffolded project directory for CLI tests |

### Markers

`db`, `pg_only`, `mysql_only`, `cli`, `redis`, `smtp`, `s3`, `rabbitmq`, `oidc`, `integration`, `slow`, `docs`

### Test Configuration

- `pytest.ini_options`: strict config/markers, `-x` fail-fast, 30s timeout
- `filterwarnings = ["error"]` with specific exceptions for aiosqlite/asyncmy/sentry_sdk
- Coverage: branch coverage, 80% threshold, `source = ["src/arvel", "tests"]`

---

## Build & Tooling

### Package Management

| Tool | Purpose |
|------|---------|
| **uv** | Dependency management, virtual env, tool installs |
| **Hatchling** | Build backend (`pyproject.toml` PEP 621) |
| **Ruff** | Linting + formatting (select: E, F, W, I, N, UP, B, A, SIM, TCH, RUF, ASYNC, S, PTH, C90, ANN) |
| **ty** | Type checking (Python 3.14 target, strict) |
| **pytest** | Test runner with anyio, coverage, timeout, xdist |
| **pre-commit** | Ruff, ty, gitleaks, standard hooks |
| **MkDocs Material** | Documentation site |

### Makefile Targets

| Target | Command |
|--------|---------|
| `make verify` | `lint + typecheck + test` (CI gate) |
| `make test-unit` | Unit tests only (no Docker) |
| `make test-docker` | Full suite against Docker services |
| `make coverage` | Tests with coverage report |
| `make lint` | Ruff check + format check |
| `make typecheck` | ty check |
| `make docs-serve` | Live-reload docs at :8001 |

### CI/CD

GitHub Actions workflows:
- CI: lint → typecheck → test on push/PR
- Docs: MkDocs build and deploy
- Release: Release Please for automated changelog + version bumps
- Dependabot for dependency updates

---

## Documentation Site

**57 pages** organized under `docs/site/en/docs/`:

| Section | Pages | Topics |
|---------|-------|--------|
| Getting Started | 4 | Installation, configuration, directory structure, deployment |
| Basics | 7 | Routing, controllers, requests, responses, middleware, validation, error handling, logging |
| Architecture | 3 | Container, providers, lifecycle |
| Database | 5 | Getting started, query builder, pagination, migrations, seeding |
| ORM | 7 | Getting started, relationships, scopes, observers, collections, mutators, soft deletes, factories |
| Security | 4 | Authentication, authorization, encryption, hashing |
| Observability | 2 | Logging, health checks |
| Digging Deeper | 8 | CLI, events, queues, scheduling, mail, notifications, cache, file storage, helpers |
| Testing | 4 | Getting started, HTTP tests, database testing, fakes |
| Guides | 4 | Architecture overview, type safety analysis, ORM best practices, testing best practices, API reference |
| Prologue | 3 | Release notes, contribution guide, upgrade guide |
| Reference | 1 | API index (placeholder) |

---

## Design Patterns

| Pattern | Where Used |
|---------|------------|
| **Active Record** | `ArvelModel` class methods (`create`, `find`, `update`, `delete`) |
| **Repository** | `Repository[T]` with typed CRUD and observer dispatch |
| **Query Object** | `QueryBuilder[T]` with fluent API |
| **Unit of Work** | `Transaction` context manager with nested savepoints |
| **Observer** | `ModelObserver[T]` + `ObserverRegistry` for lifecycle events |
| **Service Provider** | `ServiceProvider.register()` / `boot()` for DI configuration |
| **Constructor Injection** | `Container.resolve()` with `Annotated` unwrapping |
| **Pipeline (Onion)** | `Pipeline` for middleware, config loading, request processing |
| **Contract/Driver** | Every infrastructure service (cache, mail, queue, storage, lock, search) |
| **Guard** | `GuardContract` for pluggable authentication strategies |
| **Factory** | `ModelFactory` for test data generation |
| **Facade** | `Log` for structured logging API |

---

## Type Safety Strategy

### What's Enforced

- **`Mapped[T]` + `mapped_column()`** on all model columns
- **`Generic[T]`** on `Repository[T]`, `QueryBuilder[T]`, `ModelObserver[T]`
- **`Self`** for fluent/chaining APIs (`QueryBuilder`, `Pipeline`, `Transaction`)
- **`@overload`** where return type depends on input
- **Explicit re-exports** with `X as X` pattern in `__init__.py`
- **Ruff ANN** rules for missing type annotations
- **ty** type checker in CI (zero errors)

### Known Gaps

- `dict[str, Any]` for CRUD payloads (framework can't know model columns at compile time)
- `Pipeline` passable is type-erased (documented ADR)
- `setattr` in mass assignment paths (dynamically typed by nature)
- `__getattr__` on `Transaction` for repo access returns `Any`

### Tooling

- **ty** (Red Knot): Python 3.14 target, strict mode, zero errors on `src/arvel/`
- **Ruff ANN**: Missing annotation warnings in lint
- **`TypeGuard`** for runtime type narrowing

---

## Code Quality Metrics

| Metric | Value | Target |
|--------|-------|--------|
| Test count | 2,877 | — |
| Test coverage | 81.00% | 80% (threshold) |
| Lint | All checks passed | Zero warnings |
| Type check | All checks passed | Zero errors |
| Files formatted | 511/511 | 100% |
| Source files | 281 `.py` | — |
| Test files | 195 `.py` | — |
| Doc pages | 57 | — |
| Files > 500 lines | 5 | 0 (guideline) |
| Files at 0% coverage | 8 | 0 |
| Cyclomatic complexity | < 10 (enforced by Ruff C90) | < 10 |

---

## Review Findings Summary

Full deep review completed with 24 findings across 7 sections.

### Critical (Must Fix)

| # | Issue | Location | Decision |
|---|-------|----------|----------|
| 9 | Rate limiter trusts `X-Forwarded-For` without proxy validation | `security/rate_limit.py` | Add `trusted_proxies` parameter |

### Warnings (Should Fix)

| # | Issue | Location | Decision |
|---|-------|----------|----------|
| 1 | JwtGuard swallows all decode exceptions | `auth/guards/jwt_guard.py` | Catch specific PyJWT exceptions |
| 2 | Queued event listeners silently skipped | `events/dispatcher.py` | Integrate with QueueContract |
| 3 | QueryBuilder hardcodes `id` as PK | `data/query.py` | Resolve PK dynamically |
| 4 | Observer registry name collision risk | `data/observer.py` | Use `module.name` key |
| 5 | `model.py` at 934 lines (limit 500) | `data/model.py` | Split into focused modules |
| 6 | 300 lines of embedded AES in encryption | `security/encryption.py` | Extract to `_aes_fallback.py` |
| 7 | `query.py` and `router.py` exceed 500 lines | `data/query.py`, `http/router.py` | Extract RecursiveQueryBuilder + resource routing |
| 10 | Missing `WWW-Authenticate` header on 401 | `auth/guards/jwt_guard.py` | Add header (5-minute fix) |
| 11 | MAC key derivation undocumented | `security/encryption.py` | Document + consider HKDF |
| 12 | `extra_claims` can override standard JWT claims | `auth/tokens.py` | Filter reserved claims |
| 13 | `setattr` for typed attribute updates | `data/model.py`, `data/repository.py` | Add TypeGuard validation |
| 16 | Observer lifecycle mismatch (model vs repo) | `data/model.py`, `data/repository.py` | Add saving/saved to Repository |
| 17 | `new.py` 729 lines of hardcoded config | `cli/commands/new.py` | Extract to data files |
| 18 | 8 files at 0% coverage | Various | Add basic tests |
| 20 | `Repository.all()` unbounded | `data/repository.py` | Add default limit + warning |
| 21 | Rate limit store never expires stale entries | `security/rate_limit.py` | Add periodic cleanup |
| 23 | README badge version drift | `README.md` | Update badge |
| 24 | No API reference docs | `docs/reference/` | Configure mkdocstrings |

### Suggestions (Consider)

| # | Issue | Location | Decision |
|---|-------|----------|----------|
| 8 | Logger naming inconsistency | Multiple files | Standardize to `_logger` |
| 14 | `dict[str, Any]` for CRUD payloads | model, repository | Add `@overload` for TypedDicts |
| 15 | Pipeline type erasure | `foundation/pipeline.py` | Accept ADR, document typed alternative |
| 19 | `integration_health.py` top-level imports | `observability/integration_health.py` | Lazy-load inside check functions |
| 22 | Per-block crypto import | `security/encryption.py` | Module-level availability check |

---

## Dependency Map

### Core Dependencies

| Package | Purpose | Version |
|---------|---------|---------|
| FastAPI | HTTP framework | >= 0.135.3 |
| SQLAlchemy[asyncio] | ORM | >= 2.0.49 |
| Alembic | Migrations | >= 1.18.4 |
| Pydantic | Validation, settings, schemas | >= 2.12.5 |
| pydantic-settings | Env-based configuration | >= 2.13.1 |
| structlog | Structured logging | >= 25.5.0 |
| Typer | CLI | >= 0.24.1 |
| uvicorn[standard] | ASGI server | >= 0.44.0 |
| PyJWT | JWT tokens | >= 2.12.1 |
| bcrypt | Password hashing | >= 5.0.0 |
| httpx | HTTP client | >= 0.28.1 |
| Jinja2 | Code generation templates | >= 3.1.6 |
| orjson | Fast JSON serialization | >= 3.11.8 |
| anyio | Async runtime abstraction | >= 4.13.0 |
| croniter | Cron expression parsing | >= 6.2.2 |

### Optional Extras

| Extra | Packages |
|-------|----------|
| `sqlite` | aiosqlite |
| `pg` | asyncpg |
| `mysql` | asyncmy, pymysql |
| `redis` | redis[hiredis] |
| `smtp` | aiosmtplib |
| `s3` | aiobotocore |
| `media` | Pillow |
| `argon2` | argon2-cffi |
| `meilisearch` | meilisearch-python-sdk |
| `elasticsearch` | elasticsearch[async] |
| `taskiq` | taskiq, taskiq-redis |
| `otel` | opentelemetry-api, opentelemetry-sdk, opentelemetry-instrumentation-fastapi, opentelemetry-exporter-otlp-proto-grpc |
| `sentry` | sentry-sdk[fastapi] |

### Dev Dependencies

| Package | Purpose |
|---------|---------|
| pytest, pytest-cov, pytest-timeout, pytest-xdist | Testing |
| dirty-equals | Structured assertions |
| polyfactory | Model factories |
| Ruff | Lint + format |
| ty | Type checking |
| pre-commit | Git hooks |
| coverage | Coverage reporting |

---

## File Structure

```
arvel/
├── src/arvel/               # Framework source (281 .py files)
│   ├── foundation/          # Application, Container, Provider, Pipeline, Config
│   ├── data/                # ArvelModel, Repository, QueryBuilder, migrations
│   ├── http/                # Router, Kernel, Middleware, Controller, Resources
│   ├── auth/                # Guards (JWT), OAuth, Tokens, Policies, Audit
│   ├── security/            # Hashing, Encryption, Rate Limiting, CSRF
│   ├── queue/               # Jobs, Drivers (sync/taskiq), Manager, Worker
│   ├── search/              # SearchBuilder, Drivers (meilisearch/elastic/collection)
│   ├── media/               # Image pipeline, Models, Mixins
│   ├── broadcasting/        # Channels, Drivers (memory/redis/log/null)
│   ├── notifications/       # Dispatcher, Channels (mail/slack/database)
│   ├── observability/       # Logging, Health, Tracing, Sentry, Request ID
│   ├── mail/                # Contracts, SMTP/Null/Log drivers, Mailable
│   ├── storage/             # Local/S3/Managed S3, Contracts, Fakes
│   ├── events/              # Dispatcher, Event, Listener, Discovery
│   ├── cache/               # Contracts, Memory/Redis/Null drivers
│   ├── lock/                # Contracts, Memory/Redis/Null drivers
│   ├── validation/          # Validator, FormRequest, Rules (conditional/database)
│   ├── context/             # Context store, Deferred, Middleware
│   ├── testing/             # TestClient, ModelFactory, Fakes
│   ├── scheduler/           # Cron scheduler, Entries, Locks
│   ├── logging/             # Log facade, Channels, Context
│   ├── audit/               # AuditService, Entry, Mixin
│   ├── activity/            # Recorder, Entry, Migration
│   ├── i18n/                # Translator, Middleware
│   ├── support/             # Utilities, Type guards
│   ├── cli/                 # Typer app, Commands, Templates (Jinja2 stubs)
│   ├── contracts/           # Infrastructure contract re-exports
│   ├── infra/               # InfrastructureProvider
│   └── session/             # Session config
├── tests/                   # Test suite (195 .py files, 2877 tests)
├── docs/                    # MkDocs site (57 pages)
├── .github/                 # CI, Dependabot, PR template
├── pyproject.toml           # PEP 621 metadata, Ruff, ty, pytest, coverage
├── Makefile                 # Dev workflow automation
├── Dockerfile               # Container build
├── docker-compose.yml       # Dev services (Postgres, MariaDB, Valkey, Mailpit, Keycloak, MinIO)
└── CHANGELOG.md             # Release Please managed
```
