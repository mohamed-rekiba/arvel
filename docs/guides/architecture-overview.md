# Architecture Overview

This document describes Arvel's internal architecture — how the framework boots, processes requests, and manages dependencies. Read this to understand the "why" behind the design, not just the "how" of using it.

---

## High-Level Architecture

Arvel is organized into five distinct layers, each with clear responsibilities:

```mermaid
graph TB
    subgraph HTTP["HTTP Layer"]
        Router --> Middleware
        Middleware --> Controller
        Controller --> JsonResource
    end

    subgraph App["Application Layer"]
        Services
        Events
        Jobs
        Notifications
        Validation
    end

    subgraph Data["Data Layer"]
        ArvelModel --> Repository
        Repository --> QueryBuilder
        QueryBuilder --> AsyncSession
    end

    subgraph Infra["Infrastructure Layer"]
        Cache
        Mail
        Storage
        Queue
        Search
        Lock
        Broadcasting
    end

    subgraph Foundation["Foundation Layer"]
        Application --> Container
        Container --> ServiceProvider
        ServiceProvider --> Config
    end

    HTTP --> App
    App --> Data
    App --> Infra
    Data --> Foundation
    Infra --> Foundation
```

### Layer Responsibilities

| Layer | Owns | Depends On |
|-------|------|-----------|
| **Foundation** | Boot sequence, DI container, config, providers | Nothing (base layer) |
| **Infrastructure** | External service abstractions (cache, mail, storage, etc.) | Foundation |
| **Data** | ORM models, repositories, queries, migrations | Foundation |
| **Application** | Business logic, events, jobs, validation | Data + Infrastructure |
| **HTTP** | Routing, middleware, controllers, responses | Application |

---

## Request Lifecycle

Every HTTP request flows through this pipeline:

```mermaid
sequenceDiagram
    participant C as Client
    participant U as Uvicorn
    participant A as Application.__call__
    participant M as Global Middleware
    participant F as FastAPI Router
    participant RM as Route Middleware
    participant H as Handler/Controller

    C->>U: HTTP Request
    U->>A: ASGI scope/receive/send
    Note over A: Lazy boot on first call
    A->>M: Global middleware chain
    M->>F: FastAPI route matching
    F->>RM: Per-route middleware
    RM->>H: Handler execution
    H-->>RM: Response
    RM-->>F: Response
    F-->>M: Response
    M-->>A: Response
    A-->>U: ASGI response
    U-->>C: HTTP Response
```

### Step by Step

1. **Uvicorn** receives the request and passes it as an ASGI event to `Application.__call__`
2. **Lazy boot** — if not yet booted, acquires `_boot_lock` and runs the full bootstrap sequence
3. **Global middleware** wraps the FastAPI app in an onion model (lowest priority = outermost):
   - `RequestIdMiddleware` (10) — generates/propagates `X-Request-ID`
   - `AccessLogMiddleware` (20) — structured access log
   - `ContextMiddleware` (30) — request-scoped context store
   - `RequestScopeMiddleware` — creates a child DI container per request
4. **FastAPI routing** — matches the request to a registered route
5. **Route middleware** — per-route middleware resolved from aliases
6. **Handler/Controller** — executes the endpoint, DI parameters resolved from the request container
7. **Response flows back** through the middleware stack in reverse order
8. **Error handling** — exceptions caught by `install_exception_handlers`, converted to structured JSON

### Error Flow

```mermaid
flowchart LR
    E[Exception] --> EH[ExceptionHandler]
    EH --> SL[structlog error log]
    EH --> JR[JSON error response]
    JR --> C[Client receives 4xx/5xx]
    SL --> SM[ServerErrorMiddleware re-raise]
    SM --> AB[Application absorbs re-raise]
```

Arvel's `Application.__call__` absorbs the Starlette `ServerErrorMiddleware` re-raise after a response has been sent. This prevents duplicate tracebacks in Uvicorn while keeping the structured log entry from the exception handler.

---

## Boot Sequence

```mermaid
stateDiagram-v2
    [*] --> Configured: Application.configure(base_path)
    Configured --> Booting: First ASGI event
    Booting --> LoadConfig: load_config()
    LoadConfig --> EarlyLog: _apply_early_log_level()
    EarlyLog --> LoadProviders: _load_providers()
    LoadProviders --> SortProviders: Sort by priority
    SortProviders --> Configure: provider.configure(config)
    Configure --> Register: provider.register(builder)
    Register --> BuildContainer: builder.build()
    BuildContainer --> BuildFastAPI: _build_fastapi_app()
    BuildFastAPI --> BootProviders: provider.boot(app)
    BootProviders --> Booted: _booted = True
    Booted --> Serving: Handle requests
    Serving --> Shutdown: Lifespan shutdown
    Shutdown --> [*]: provider.shutdown() + container.close()
```

### Why Lazy Boot?

`Application.configure()` is **synchronous** and returns immediately. The async bootstrap runs on the first ASGI event. This design means:

- No async work at import time (uvicorn factory compatibility)
- No FastAPI leaking to user code
- Process managers (systemd, supervisord) get immediate process startup
- Tests can use `Application.create()` for eager async bootstrap

---

## DI Container Architecture

```mermaid
classDiagram
    class ContainerBuilder {
        +provide(interface, concrete, scope)
        +provide_factory(interface, factory, scope)
        +provide_value(interface, value, scope)
        +build() Container
    }

    class Container {
        -_bindings: dict
        -_instances: dict
        -_scope: Scope
        -_parent: Container
        +resolve(interface) T
        +enter_scope(scope) Container
        +instance(interface, value)
        +close()
    }

    class Scope {
        <<enumeration>>
        APP
        REQUEST
        SESSION
    }

    ContainerBuilder --> Container : builds
    Container --> Container : parent chain
    Container --> Scope : scoped
```

### Scope Resolution

When `resolve(T)` is called:

1. Check local `_instances` cache
2. Look up `_bindings` for `T`
3. If binding scope is higher than current scope, delegate to parent
4. Create instance (factory or constructor injection)
5. Cache in `_instances`

```
APP Container (singleton)
  ├── DatabaseEngine
  ├── AppSettings
  └── REQUEST Container (per-request)
       ├── AsyncSession
       ├── UserRepository
       └── SESSION Container (per-user)
            └── UserPreferences
```

### Constructor Injection

The container uses `get_type_hints(cls.__init__)` to discover dependencies:

```python
class OrderService:
    def __init__(
        self,
        repo: OrderRepository,       # Resolved from container
        mailer: MailContract,         # Resolved from container
        cache: CacheContract,         # Resolved from container
    ) -> None:
        self.repo = repo
        self.mailer = mailer
        self.cache = cache
```

Type hints are cached per class via `@lru_cache` on `_get_init_hints`. `Annotated[T, ...]` is unwrapped to resolve `T`.

---

## Provider System

```mermaid
flowchart LR
    subgraph Lifecycle
        C[configure] --> R[register]
        R --> B[boot]
        B --> S[shutdown]
    end

    subgraph register
        R1[Declare bindings]
        R2[No resolution allowed]
    end

    subgraph boot
        B1[Resolve dependencies]
        B2[Wire routes]
        B3[Register middleware]
        B4[Start listeners]
    end

    R --> R1 & R2
    B --> B1 & B2 & B3 & B4
```

### Provider Priority Bands

| Band | Priority | Purpose | Examples |
|------|----------|---------|---------|
| Core | 0–5 | Essential infrastructure | Observability, Context |
| Data | 10 | Database, sessions | DatabaseServiceProvider |
| Security | 12 | Auth, encryption | SecurityProvider |
| HTTP | 15 | Routing, middleware | HttpServiceProvider |
| Services | 20 | Application services | SearchProvider |
| User | 50 | Application code | AppProvider |

---

## Data Layer Architecture

```mermaid
classDiagram
    class ArvelModel {
        +__tablename__: str
        +__fillable__: set
        +__guarded__: set
        +created_at: datetime
        +updated_at: datetime
        +query(session) QueryBuilder
        +model_validate(data) Self
        +model_dump() dict
    }

    class Repository~T~ {
        -_session: AsyncSession
        -_observer_registry: ObserverRegistry
        +create(data) T
        +find(id) T | None
        +find_or_fail(id) T
        +update(instance, data) T
        +delete(instance) bool
        +query() QueryBuilder~T~
    }

    class QueryBuilder~T~ {
        +where(*criteria) Self
        +order_by(*columns) Self
        +limit(n) Self
        +offset(n) Self
        +with_(*relations) Self
        +has(relation, op, count) Self
        +where_has(relation, callback) Self
        +all() list~T~
        +first() T | None
        +count() int
        +with_count(*relations) Self
        +recursive() Self
    }

    class Transaction {
        -_session: AsyncSession
        +nested() SavepointContext
        +users: UserRepository
        +posts: PostRepository
    }

    ArvelModel <|-- User
    ArvelModel <|-- Post
    Repository --> QueryBuilder : creates
    Repository --> ArvelModel : operates on
    Transaction --> Repository : provides
    QueryBuilder --> AsyncSession : executes
```

### Query Execution Flow

```
User code                       QueryBuilder                 SQLAlchemy
─────────                       ────────────                 ──────────
query.where(User.active)  →  stmt.where(clause)
query.order_by(User.name)  → stmt.order_by(col)
query.limit(20)            →  stmt.limit(20)
query.all()                →  session.execute(stmt)    →  SQL generation
                           ←  result.scalars().all()   ←  Database result
                           →  ArvelCollection(rows)
```

### Observer Dispatch

```
Repository.create(data)
    │
    ├── dispatch("creating", instance) → abort if False
    │
    ├── session.add(instance)
    ├── session.flush()
    │
    └── dispatch("created", instance)
```

---

## Contract / Driver Pattern

Every infrastructure concern follows the same pattern:

```mermaid
classDiagram
    class Contract {
        <<interface>>
    }

    class MemoryDriver {
    }

    class RedisDriver {
    }

    class NullDriver {
    }

    class Fake {
        +assertions
    }

    Contract <|.. MemoryDriver
    Contract <|.. RedisDriver
    Contract <|.. NullDriver
    Contract <|.. Fake
```

| Contract | Drivers | Fake |
|----------|---------|------|
| `CacheContract` | memory, redis, null | `CacheFake` |
| `QueueContract` | sync, null, taskiq | `QueueFake` |
| `MailContract` | smtp, log, null | `MailFake` |
| `StorageContract` | local, s3, null | `StorageFake` |
| `LockContract` | memory, redis, null | `LockFake` |
| `BroadcastContract` | redis, memory, log, null | `BroadcastFake` |
| `SearchEngine` | meilisearch, elasticsearch, database, collection, null | — |
| `NotificationContract` | mail, database, slack | `NotificationFake` |
| `MediaContract` | — | `MediaFake` |

This design means:

- **Development**: Use memory/null drivers (no external services)
- **Testing**: Use fakes with assertion APIs
- **Production**: Use real drivers (Redis, S3, SMTP, etc.)
- **Swappable**: Change a driver by updating one env var

---

## Module Map

```
src/arvel/
├── foundation/     # Application kernel, DI container, providers, config, pipeline
├── http/           # Router, middleware, controllers, resources, exception handling
├── data/           # ORM models, repository, query builder, relationships, observers
├── auth/           # Guards, JWT, OAuth, policies, password reset, audit
├── validation/     # Form requests, rules, validator
├── events/         # Event dispatcher, listeners, discovery
├── broadcasting/   # Real-time broadcasting with channels
├── queue/          # Jobs, batching, chaining, middleware, workers
├── scheduler/      # Cron-based task scheduling
├── cache/          # Cache contract and drivers
├── lock/           # Distributed lock contract and drivers
├── mail/           # Mailable, drivers, attachments
├── notifications/  # Multi-channel notification dispatch
├── storage/        # File storage abstraction
├── search/         # Full-text search with engine drivers
├── media/          # Polymorphic file attachments
├── security/       # Encryption, hashing, CSRF, rate limiting
├── observability/  # Logging, tracing, health checks, Sentry
├── context/        # Request-scoped context, deferred tasks
├── i18n/           # Internationalization / translation
├── session/        # Session management
├── activity/       # Activity logging
├── audit/          # Audit trail
├── testing/        # TestClient, factories, fakes
├── support/        # Utilities, type guards
├── cli/            # Typer CLI, commands, code generators
├── app/            # Root configuration
├── contracts/      # Infrastructure contract re-exports
├── infra/          # Infrastructure wiring provider
└── logging/        # Log facade
```

Each module follows the same internal structure:

```
module/
├── __init__.py      # Public API re-exports
├── config.py        # ModuleSettings (pydantic-settings)
├── contracts.py     # Abstract interface
├── provider.py      # ServiceProvider for DI registration
├── drivers/         # Concrete implementations
│   ├── memory.py
│   ├── redis.py
│   └── null.py
├── fakes.py         # Test doubles with assertions
└── exceptions.py    # Module-specific errors
```

---

*This architecture document reflects Arvel v0.1.5. The framework is under active development — APIs may change before 1.0.*
