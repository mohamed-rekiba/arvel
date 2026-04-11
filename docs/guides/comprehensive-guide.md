# Arvel Framework — Comprehensive Documentation

**Version**: 0.1.5 | **Python**: 3.14+ | **License**: MIT

Arvel is an async-first, type-safe Python web framework inspired by Laravel, built on top of FastAPI, SQLAlchemy 2.0, and Pydantic. It brings Laravel's batteries-included ergonomics to modern async Python with end-to-end type safety.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Concepts](#core-concepts)
3. [Application Lifecycle](#application-lifecycle)
4. [Dependency Injection Container](#dependency-injection-container)
5. [Service Providers](#service-providers)
6. [HTTP Layer](#http-layer)
7. [ORM & Data Layer](#orm--data-layer)
8. [Authentication & Authorization](#authentication--authorization)
9. [Validation](#validation)
10. [Events & Broadcasting](#events--broadcasting)
11. [Queue & Scheduler](#queue--scheduler)
12. [Cache, Sessions & Locks](#cache-sessions--locks)
13. [Mail & Notifications](#mail--notifications)
14. [File Storage](#file-storage)
15. [Search](#search)
16. [Observability](#observability)
17. [Security](#security)
18. [CLI](#cli)
19. [Testing](#testing)
20. [Configuration Reference](#configuration-reference)
21. [Project Structure](#project-structure)
22. [Tech Stack](#tech-stack)

---

## Architecture Overview

Arvel follows a **layered modular architecture** with clear separation of concerns:

```
┌──────────────────────────────────────────────────────────────────┐
│                        HTTP Layer                                │
│   Router → Middleware Pipeline → Controller → JsonResource        │
├──────────────────────────────────────────────────────────────────┤
│                     Application Layer                            │
│   Services │ Events │ Jobs │ Notifications │ Validation          │
├──────────────────────────────────────────────────────────────────┤
│                      Data Layer                                  │
│   ArvelModel → Repository → QueryBuilder → AsyncSession          │
├──────────────────────────────────────────────────────────────────┤
│                   Infrastructure Layer                           │
│   Cache │ Mail │ Storage │ Queue │ Search │ Lock │ Broadcasting  │
├──────────────────────────────────────────────────────────────────┤
│                     Foundation Layer                              │
│   Application Kernel │ DI Container │ ServiceProviders │ Config  │
└──────────────────────────────────────────────────────────────────┘
```

### Design Principles

- **Async-first**: Every I/O operation is async. No blocking calls in the hot path.
- **Type-safe**: `Mapped[T]` columns, generic repositories, typed query builders — your IDE and `ty` catch errors before runtime.
- **Contract-driven**: Every infrastructure concern (cache, mail, storage, queue, etc.) is defined by a contract interface with swappable drivers.
- **Provider-based bootstrapping**: Modules register DI bindings in `register()` and wire runtime behavior in `boot()`. No import-time side effects.
- **Convention over configuration**: Table names, FK columns, pivot tables, and more follow Laravel-inspired conventions that can be overridden when needed.

### Key Dependencies

| Layer | Technology | Purpose |
|-------|-----------|---------|
| HTTP | FastAPI + Starlette + Uvicorn | ASGI server, routing, OpenAPI |
| ORM | SQLAlchemy 2.0 (async) | Typed models, relationships, queries |
| Migrations | Alembic | Schema versioning |
| Validation | Pydantic + pydantic-settings | Request validation, app config |
| CLI | Typer | Command-line interface |
| Logging | structlog | Structured logging |
| Serialization | orjson | Fast JSON encoding |
| Auth | PyJWT + bcrypt | Token management, password hashing |

---

## Core Concepts

### The Application Kernel

`Application` is the entry point for every Arvel app. It implements the ASGI protocol directly, lazy-bootstrapping on the first request:

```python
from arvel.foundation import Application

# For uvicorn (sync factory — no async at import time)
app = Application.configure(".")

# For tests or scripts (eager async bootstrap)
app = await Application.create(".", testing=True)
```

The `configure()` method returns an ASGI-compatible object immediately. The heavy async work (config loading, provider lifecycle, FastAPI construction) runs automatically on the first ASGI event. This means uvicorn and process managers stay predictable.

### Lazy Bootstrap Sequence

1. **Config loading** — reads `.env`, loads `AppSettings` and all `ModuleSettings` from `config/` modules
2. **Early logging** — sets up minimal structlog → stdlib bridge so provider lifecycle messages are filtered correctly
3. **Provider registration** — each provider declares DI bindings on the `ContainerBuilder`
4. **Container build** — `ContainerBuilder.build()` freezes bindings into an immutable `Container`
5. **Provider boot** — each provider wires routes, middleware, listeners, and resolved dependencies
6. **FastAPI construction** — builds the `FastAPI` app with metadata, lifespan, and OpenAPI security schemes
7. **Application marked booted** — subsequent ASGI calls go directly to FastAPI

### Provider File

Every Arvel app must have `bootstrap/providers.py` that exports a `providers` list:

```python
from arvel.foundation.provider import ServiceProvider

class AppProvider(ServiceProvider):
    async def register(self, container) -> None:
        # Declare DI bindings here
        pass

    async def boot(self, app) -> None:
        # Wire routes, listeners, middleware here
        pass

providers = [AppProvider]
```

---

## Application Lifecycle

```
┌─────────────────────────────────────────────────┐
│           Application.configure(base_path)       │
│  (sync — returns ASGI app immediately)           │
└──────────────────┬──────────────────────────────┘
                   │ first ASGI event
                   ▼
┌─────────────────────────────────────────────────┐
│           _bootstrap() (async)                   │
│  1. load_config() → AppSettings + ModuleSettings │
│  2. _apply_early_log_level()                     │
│  3. _load_providers() from bootstrap/providers.py│
│  4. Sort providers by priority                   │
│  5. provider.configure(config) for each          │
│  6. provider.register(builder) for each          │
│  7. builder.build() → Container                  │
│  8. _build_fastapi_app(config)                   │
│  9. _boot_providers()                            │
│ 10. _booted = True                               │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│        Request handling (FastAPI)                 │
│  scope → receive → _track_send → response        │
└──────────────────┬──────────────────────────────┘
                   │ lifespan shutdown
                   ▼
┌─────────────────────────────────────────────────┐
│           shutdown() (async)                     │
│  1. Reverse-order provider.shutdown()            │
│  2. container.close()                            │
│  3. _shutdown_complete = True                    │
└─────────────────────────────────────────────────┘
```

### Provider Priority

Providers boot in priority order (lower number = earlier). Framework providers use 0–20; user providers default to 50:

```python
class ServiceProvider:
    priority: int = 50  # default for user providers

    def configure(self, config: AppSettings) -> None: ...
    async def register(self, container: ContainerBuilder) -> None: ...
    async def boot(self, app: Application) -> None: ...
    async def shutdown(self, app: Application) -> None: ...
```

---

## Dependency Injection Container

The DI container provides constructor injection with three lifetime scopes:

| Scope | Lifetime | Use Case |
|-------|----------|----------|
| `APP` | Application singleton | Database engine, config, global services |
| `REQUEST` | Per HTTP request | Request-scoped session, auth context |
| `SESSION` | Per user session | User-specific caches |

### Registration (during `register()`)

```python
from arvel.foundation.container import ContainerBuilder, Scope

async def register(self, container: ContainerBuilder) -> None:
    # Interface → concrete class binding
    container.provide(CacheContract, RedisCacheDriver, scope=Scope.APP)

    # Factory binding
    container.provide_factory(
        AsyncSession,
        lambda: async_session_maker(),
        scope=Scope.REQUEST,
    )

    # Pre-built value
    container.provide_value(AppSettings, config, scope=Scope.APP)
```

### Resolution

```python
# Explicit resolution
cache = await container.resolve(CacheContract)

# Constructor injection (automatic)
class UserService:
    def __init__(self, repo: UserRepository, cache: CacheContract) -> None:
        self.repo = repo
        self.cache = cache

# The container resolves constructor parameters automatically via type hints
service = await container.resolve(UserService)
```

### Request-Scoped Containers

`RequestScopeMiddleware` creates a child container for each HTTP request:

```python
# In a controller, use Inject() to resolve from the request container
from arvel.http.controller import Inject

async def create_user(
    payload: CreateUserRequest,
    user_service: UserService = Inject(UserService),
) -> UserResponse:
    return await user_service.create(payload)
```

### How Constructor Injection Works

The container introspects `__init__` type hints using `get_type_hints()`. For each parameter:

1. If the type is `Annotated[T, ...]`, unwrap to `T`
2. Resolve `T` from the container
3. If resolution fails and the parameter has a default, skip it
4. If resolution fails and no default, raise `DependencyError`

Results are cached per class via `@lru_cache` on `_get_init_hints`.

---

## Service Providers

Providers are the modular building blocks of an Arvel application. Each provider manages a specific concern:

### Framework Providers

| Provider | Module | Priority | Purpose |
|----------|--------|----------|---------|
| `ObservabilityProvider` | `arvel.observability` | 0 | Logging, tracing, health checks, Sentry |
| `ContextProvider` | `arvel.context` | 5 | Request context, deferred tasks |
| `DatabaseServiceProvider` | `arvel.data` | 10 | Session factory, observer registry |
| `HttpServiceProvider` | `arvel.http` | 15 | Router, middleware stack, exception handlers |
| `SecurityProvider` | `arvel.security` | 12 | Hashing, encryption, CSRF, rate limiting |
| `SearchProvider` | `arvel.search` | 20 | Search engine registration |

### Provider Lifecycle

```python
class MyProvider(ServiceProvider):
    priority = 50

    def configure(self, config: AppSettings) -> None:
        """Capture config before registration. Called synchronously."""
        self._settings = get_module_settings(config, MySettings)

    async def register(self, container: ContainerBuilder) -> None:
        """Declare DI bindings. The container isn't built yet — don't resolve."""
        container.provide(MyContract, MyImplementation, scope=Scope.APP)

    async def boot(self, app: Application) -> None:
        """Late-stage wiring. Container is built — resolve dependencies here."""
        router = await app.container.resolve(Router)
        router.get("/my-endpoint", my_handler)

    async def shutdown(self, app: Application) -> None:
        """Release resources. Called in reverse provider order."""
        await self._connection_pool.close()
```

---

## HTTP Layer

### Router

The `Router` wraps FastAPI's routing with Laravel-style ergonomics:

```python
from arvel.http.router import Router

router = Router()

# Basic routes
router.get("/users", list_users, name="users.index")
router.post("/users", create_user, name="users.store")
router.get("/users/{user_id}", show_user, name="users.show")
router.put("/users/{user_id}", update_user, name="users.update")
router.delete("/users/{user_id}", delete_user, name="users.destroy")

# Route groups with shared prefix and middleware
with router.group(prefix="/api/v1", middleware=["auth", "throttle"]):
    router.get("/profile", get_profile, name="profile.show")

# Resource routes (generates all CRUD routes)
router.resource("/posts", PostController)
```

### Route Discovery

Routes are auto-discovered from `routes/*.py` files. Each file must export a `router` instance:

```python
# routes/web.py
from arvel.http.router import Router

router = Router()
router.get("/", lambda: {"message": "Welcome"}, name="home")

# routes/api.py
from arvel.http.router import Router

router = Router(prefix="/api/v1")
router.get("/health", health_check, name="api.health")
```

### Controllers

Class-based controllers with DI:

```python
from arvel.http.controller import BaseController, Inject, route

class UserController(BaseController):
    prefix = "/users"
    tags = ("Users",)
    middleware = ("auth",)

    @route.get("/")
    async def index(self, repo: UserRepository = Inject(UserRepository)):
        return await repo.query().limit(20).all()

    @route.post("/")
    async def store(
        self,
        payload: CreateUserRequest,
        service: UserService = Inject(UserService),
    ):
        return await service.create(payload)

    @route.get("/{user_id}")
    async def show(self, user_id: int, repo: UserRepository = Inject(UserRepository)):
        return await repo.find_or_fail(user_id)
```

### Middleware

All middleware is pure ASGI — no `BaseHTTPMiddleware`:

```python
from starlette.types import ASGIApp, Receive, Scope, Send

class TimingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        await self.app(scope, receive, send)
        duration = time.monotonic() - start
        logger.info("request_duration", duration_ms=round(duration * 1000, 2))
```

Middleware is registered via aliases in `HttpSettings`:

```python
# config/http.py
middleware_aliases = {
    "auth": "app.middleware.auth.AuthMiddleware",
    "throttle": "arvel.security.rate_limit.RateLimitMiddleware",
}
middleware_groups = {
    "api": ["auth", "throttle"],
}
global_middleware = [
    ("request_id", 10),
    ("access_log", 20),
    ("context", 30),
]
```

### Pipeline

The `Pipeline` class implements ordered pipe processing for middleware and workflows:

```python
from arvel.foundation.pipeline import Pipeline

result = await (
    Pipeline(container)
    .send(request)
    .through([ValidateInput, TransformData, SaveToDatabase])
    .then(final_handler)
)
```

Pipes can be async callables, sync callables, or class references resolved via DI.

### JSON Resources

Transform model instances into API responses:

```python
from arvel.http.resources import JsonResource, ResourceCollection

class UserResource(JsonResource[User]):
    def to_dict(self, instance: User) -> dict:
        return {
            "id": instance.id,
            "name": instance.name,
            "email": instance.email,
            "created_at": instance.created_at.isoformat(),
        }

# Single resource
return UserResource(user).to_response()

# Collection with pagination
return ResourceCollection(UserResource, users, pagination).to_response()
```

---

## ORM & Data Layer

### Model Definition

All models extend `ArvelModel` (SQLAlchemy 2.0 `DeclarativeBase`) with automatic Pydantic schema generation:

```python
from arvel.data.model import ArvelModel
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

class User(ArvelModel):
    __tablename__ = "users"
    __fillable__ = {"name", "email", "bio"}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    bio: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(default=True)
    # created_at and updated_at are provided automatically
```

**Key conventions:**

| Convention | Rule | Example |
|-----------|------|---------|
| Table names | Plural snake_case | `users`, `blog_posts` |
| FK columns | `{related_singular}_id` | `user_id`, `post_id` |
| Pivot tables | Alphabetical singular join | `role_user`, `post_tag` |
| Timestamps | Auto-provided | `created_at`, `updated_at` |

### Mass Assignment Protection

```python
class User(ArvelModel):
    # Only these fields can be mass-assigned
    __fillable__ = {"name", "email", "bio"}
    # OR guard these fields (everything else is fillable)
    __guarded__ = {"id", "is_admin", "created_at", "updated_at"}
```

### Query Builder

`QueryBuilder[T]` provides a fluent, type-safe query API:

```python
# Basic queries
users = await User.query(session).where(User.is_active == True).order_by(User.name).all()
user = await User.query(session).where(User.id == 1).first()
count = await User.query(session).where(User.is_active == True).count()

# Eager loading
users = await (
    User.query(session)
    .with_("posts", "posts.comments", "profile")
    .where(User.is_active == True)
    .limit(20)
    .all()
)

# Relationship filtering
users_with_posts = await (
    User.query(session)
    .where_has("posts", lambda Post: Post.is_published == True)
    .has("comments", ">", 5)
    .all()
)

# Aggregation
users_with_counts = await (
    User.query(session)
    .with_count("posts", "comments")
    .all_with_counts()
)
for row in users_with_counts:
    print(f"{row.instance.name}: {row.counts['posts']} posts")

# Recursive CTEs (tree structures)
descendants = await (
    Category.query(session)
    .descendants(root_id=1, parent_col="parent_id")
    .all()
)

# Debug SQL output
sql = User.query(session).where(User.name == "Alice").to_sql()
```

### Repository

One repository per model. The session is private — callers never touch `AsyncSession`:

```python
from arvel.data.repository import Repository

class UserRepository(Repository[User]):
    async def find_by_email(self, email: str) -> User | None:
        return await self.query().where(User.email == email).first()

    async def find_active(self) -> list[User]:
        return await self.query().where(User.is_active == True).all()
```

**Built-in CRUD:**

```python
repo = UserRepository(session=session, observer_registry=registry)

# Create
user = await repo.create({"name": "Alice", "email": "alice@example.com"})

# Read
user = await repo.find(1)          # Returns User | None
user = await repo.find_or_fail(1)  # Raises NotFoundError

# Update
user = await repo.update(user, {"name": "Alice Smith"})

# Delete
await repo.delete(user)

# Query builder access
users = await repo.query().where(User.is_active == True).limit(20).all()
```

### Relationships

```python
from arvel.data.relationships import has_one, has_many, belongs_to, belongs_to_many

class User(ArvelModel):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))

    profile: Profile = has_one("Profile", back_populates="user")
    posts: list[Post] = has_many("Post", back_populates="author")
    roles: list[Role] = belongs_to_many("Role", pivot_table="role_user")

class Post(ArvelModel):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    author: User = belongs_to("User", back_populates="posts")
    tags: list[Tag] = belongs_to_many("Tag", pivot_table="post_tag")
```

**Polymorphic relationships:**

```python
from arvel.data.relationships import morph_to, morph_many, register_morph_type

class Comment(ArvelModel):
    commentable: ArvelModel = morph_to()

class Post(ArvelModel):
    comments: list[Comment] = morph_many("Comment")

register_morph_type("post", Post)
register_morph_type("video", Video)
```

### Strict Mode

`ARVEL_STRICT_RELATIONS=true` (default) raises `LazyLoadError` on lazy access — all relationships must be eager-loaded:

```python
# Raises LazyLoadError — must use with_()
user = await repo.find(1)
posts = user.posts  # ERROR

# Correct — eager load explicitly
user = await User.query(session).with_("posts").where(User.id == 1).first()
posts = user.posts  # OK
```

### Scopes

```python
from arvel.data.scopes import scope, GlobalScope

class User(ArvelModel):
    __global_scopes__ = [ActiveScope]

    @scope
    @staticmethod
    def older_than(query: QueryBuilder, age: int) -> QueryBuilder:
        return query.where(User.age > age)

class ActiveScope(GlobalScope):
    def apply(self, query: QueryBuilder) -> QueryBuilder:
        return query.where(User.is_active == True)

# Usage
users = await User.query(session).older_than(30).all()
users = await User.query(session).without_global_scope("ActiveScope").all()
```

### Soft Deletes

```python
from arvel.data.model import ArvelModel
from arvel.data.soft_deletes import SoftDeletes

class Post(SoftDeletes, ArvelModel):
    __tablename__ = "posts"
    # deleted_at column is added automatically

# Usage
await repo.delete(post)           # Sets deleted_at, doesn't remove row
assert post.trashed                # True
await repo.restore(post)          # Clears deleted_at
await repo.force_delete(post)     # Actually removes the row

# Query filtering
posts = await Post.query(session).all()              # Excludes trashed
posts = await Post.query(session).with_trashed().all() # Includes trashed
posts = await Post.query(session).only_trashed().all() # Only trashed
```

### Observers

```python
from arvel.data.observer import ModelObserver

class UserObserver(ModelObserver[User]):
    async def creating(self, instance: User) -> bool:
        instance.email = instance.email.lower().strip()
        return True  # False aborts creation

    async def created(self, instance: User) -> None:
        await send_welcome_email(instance)

    async def deleting(self, instance: User) -> bool:
        return True  # False aborts deletion

# Registration
registry.register(User, UserObserver())
```

### Factories

```python
from arvel.testing.factory import ModelFactory

class UserFactory(ModelFactory[User]):
    __model__ = User

    @classmethod
    def defaults(cls) -> dict:
        seq = cls._next_seq()
        return {
            "name": f"User {seq}",
            "email": f"user{seq}@example.com",
            "is_active": True,
        }

    @classmethod
    def state_admin(cls) -> dict:
        return {"is_admin": True, "role": "admin"}

# Usage
user = UserFactory.make()                                    # In-memory
user = await UserFactory.create(session=session)             # Persisted
users = await UserFactory.create_many(5, session=session)    # Batch
admin = await UserFactory.state("admin").create(session=session)
```

### Collections

```python
from arvel.data.collection import ArvelCollection, collect

users = collect([user1, user2, user3])

# Transformations
names = users.pluck("name")           # ["Alice", "Bob", "Charlie"]
active = users.filter(lambda u: u.is_active)
mapped = users.map(lambda u: {"id": u.id, "name": u.name})

# Querying
first = users.first()
alice = users.first_where("name", "Alice")
grouped = users.group_by("role")
chunked = users.chunk(10)
unique = users.unique("email")
sorted_users = users.sort_by("name")
```

### Pagination

**Offset-based** (simple, fine for small datasets):

```python
from arvel.data.pagination import PaginatedResult

users = await User.query(session).limit(20).offset(40).all()
total = await User.query(session).count()
result = PaginatedResult(items=users, total=total, page=3, per_page=20)
return result.to_response()
```

**Cursor-based** (scalable for large datasets):

```python
from arvel.data.pagination import encode_cursor, CursorResult

cursor = encode_cursor("id", last_id)
users = await User.query(session).where(User.id > last_id).limit(20).all()
result = CursorResult(items=users, next_cursor=encode_cursor("id", users[-1].id))
```

### Transactions

```python
from arvel.data.transaction import Transaction

async with Transaction(session=session, observer_registry=registry) as tx:
    user = await tx.users.create({"name": "Alice", "email": "a@t.com"})

    # Savepoint for partial rollback
    async with tx.nested():
        try:
            await tx.orders.create(risky_data)
        except Exception:
            pass  # Savepoint rolls back; user survives
```

### Migrations

Alembic-based with a Laravel-friendly API:

```bash
# Generate a migration
arvel make migration create_posts_table

# Run migrations
arvel db migrate

# Rollback
arvel db rollback --steps 1

# Fresh database (drop + recreate + migrate + seed)
arvel db fresh

# Check status
arvel db status
```

Migration file example:

```python
from arvel.data.migrations import Schema

def upgrade():
    Schema.create("posts", lambda table: (
        table.id(),
        table.string("title", 255),
        table.text("body"),
        table.integer("author_id").foreign_key("users.id").index(),
        table.timestamps(),
    ))

def downgrade():
    Schema.drop("posts")
```

---

## Authentication & Authorization

### Authentication

Arvel provides a guard-based auth system:

```python
from arvel.auth import AuthManager

# JWT Guard (default)
auth = AuthManager(guards={"jwt": jwt_guard, "api_key": api_key_guard}, default="jwt")
user = await auth.authenticate(request)
token = await auth.issue_token(user)
```

**Guards:**

| Guard | Use Case |
|-------|----------|
| `JwtGuard` | JWT access/refresh tokens with configurable TTL |
| `ApiKeyGuard` | API key authentication for service-to-service calls |
| OAuth2/OIDC | External identity providers (Keycloak, Auth0, etc.) |

**JWT configuration** (via `SecuritySettings`):

```bash
SECURITY_JWT_ALGORITHM=HS256
SECURITY_JWT_ACCESS_TTL_MINUTES=60
SECURITY_JWT_REFRESH_TTL_DAYS=30
SECURITY_JWT_ISSUER=arvel
SECURITY_JWT_AUDIENCE=arvel-app
```

### OAuth2 / OIDC

```python
from arvel.auth.oauth import OAuthProviderRegistry

registry = OAuthProviderRegistry()
# Providers auto-discovered from OIDC issuer URL
```

### Authorization (Policies)

```python
from arvel.auth.policy import Policy, PolicyRegistry, Gate

class PostPolicy(Policy):
    async def update(self, user: User, post: Post) -> bool:
        return user.id == post.author_id

    async def delete(self, user: User, post: Post) -> bool:
        return user.id == post.author_id or user.is_admin

# Registration
registry = PolicyRegistry()
registry.register(Post, PostPolicy())

# Usage
gate = Gate(registry)
if not await gate.allows(user, "update", post):
    raise PermissionError("Not authorized")
```

### Password Hashing

```python
from arvel.security.hashing import BcryptHasher

hasher = BcryptHasher(rounds=12)
hashed = hasher.make("secret-password")
is_valid = hasher.check("secret-password", hashed)
needs_rehash = hasher.needs_rehash(hashed)
```

### CSRF Protection

`CsrfMiddleware` uses double-submit cookie pattern. Bearer-token API routes are excluded by default:

```bash
SECURITY_CSRF_ENABLED=true
SECURITY_CSRF_EXCLUDE_PREFIXES=["/api/"]
```

### Rate Limiting

```bash
SECURITY_RATE_LIMIT_DEFAULT=60/minute
SECURITY_RATE_LIMIT_AUTH=5/minute
```

---

## Validation

Pydantic-powered validation with custom rules:

### Form Requests

```python
from arvel.validation import FormRequest, Rule, Exists, Unique

class CreateUserRequest(FormRequest):
    name: str
    email: str

    def rules(self) -> dict:
        return {
            "name": [Rule.required(), Rule.string(), Rule.max(255)],
            "email": [Rule.required(), Rule.email(), Unique("users", "email")],
        }

    async def authorize(self) -> bool:
        return True  # Check permissions here
```

### Built-in Rules

| Rule | Purpose |
|------|---------|
| `Rule` / `AsyncRule` | Base classes for custom rules |
| `Exists` | Database existence check |
| `Unique` | Database uniqueness check |
| `RequiredIf` | Conditionally required |
| `RequiredUnless` | Required unless condition |
| `RequiredWith` | Required when another field is present |
| `ProhibitedIf` | Prohibited under condition |
| `ConditionalRule` | Base for conditional validation |

### Validator

```python
from arvel.validation import Validator

validator = Validator(data=payload, rules={
    "name": [Rule.required(), Rule.string()],
    "age": [Rule.required(), Rule.integer(), Rule.min(0), Rule.max(150)],
})
errors = await validator.validate()
if errors:
    raise ValidationError(errors=errors)
```

---

## Events & Broadcasting

### Events

Events are Pydantic models dispatched through the `EventDispatcher`:

```python
from arvel.events import Event, Listener, EventDispatcher, queued

class OrderShipped(Event):
    order_id: int
    tracking_number: str

class SendShipmentEmail(Listener):
    async def handle(self, event: OrderShipped) -> None:
        await send_email(event.order_id, event.tracking_number)

@queued
class IndexOrderInSearch(Listener):
    """Runs asynchronously via the queue."""
    async def handle(self, event: OrderShipped) -> None:
        await search.index("orders", event.order_id)

# Dispatch
dispatcher = EventDispatcher()
await dispatcher.dispatch(OrderShipped(order_id=42, tracking_number="ABC123"))
```

### Broadcasting

Real-time event broadcasting with channel authorization:

```python
from arvel.broadcasting import Broadcastable, PrivateChannel, BroadcastContract

class OrderStatusChanged(Broadcastable):
    def broadcast_on(self) -> list[str]:
        return [f"private-order.{self.order_id}"]

    def broadcast_as(self) -> str:
        return "order.status.changed"
```

**Drivers:** Redis, memory, log, null.

---

## Queue & Scheduler

### Jobs

```python
from arvel.queue import Job, QueueContract

class SendWeeklyDigest(Job):
    user_id: int

    max_retries: int = 3
    backoff: str = "exponential"
    timeout: int = 300
    queue_name: str = "emails"

    async def handle(self) -> None:
        user = await find_user(self.user_id)
        await compile_and_send_digest(user)
```

### Dispatching

```python
queue = await container.resolve(QueueContract)
await queue.push(SendWeeklyDigest(user_id=42))

# Batch processing
from arvel.queue import Batch
batch = Batch(jobs=[
    SendWeeklyDigest(user_id=1),
    SendWeeklyDigest(user_id=2),
    SendWeeklyDigest(user_id=3),
])
await queue.push_batch(batch)

# Job chaining
from arvel.queue import Chain
chain = Chain(jobs=[
    ProcessPayment(order_id=99),
    SendReceipt(order_id=99),
    NotifyWarehouse(order_id=99),
])
await queue.push_chain(chain)
```

### Job Middleware

```python
from arvel.queue import RateLimited, WithoutOverlapping

class ImportRows(Job):
    def middleware(self) -> list:
        return [
            RateLimited(max_per_minute=10),
            WithoutOverlapping(key=f"import:{self.file_id}"),
        ]
```

### Scheduler

```python
from arvel.scheduler import Scheduler, ScheduleEntry

scheduler = Scheduler()

scheduler.job(SendReminders).daily_at("08:30").timezone("America/New_York")
scheduler.job(CleanupTempFiles).hourly()
scheduler.job(GenerateReports).weekly().on("monday").at("06:00")
scheduler.job(SyncInventory).every_minutes(15).without_overlapping()
```

Run with: `arvel schedule run` (one-shot) or as a daemon.

**Drivers:** sync, null, TaskIQ (Redis/NATS/RabbitMQ).

---

## Cache, Sessions & Locks

### Cache

```python
from arvel.cache.contracts import CacheContract

# Basic operations
await cache.put("key", value, ttl=3600)
value = await cache.get("key")
await cache.forget("key")
await cache.flush()

# Remember pattern (cache-aside)
stats = await cache.remember("dashboard.stats", ttl=300, callback=compute_stats)

# Check existence
if await cache.has("key"):
    ...
```

**Drivers:** memory (in-process), Redis, null.

### Sessions

```bash
SESSION_DRIVER=memory
SESSION_LIFETIME=120
SESSION_COOKIE=arvel_session
SESSION_SECURE=false
SESSION_HTTP_ONLY=true
SESSION_SAME_SITE=lax
```

### Distributed Locks

```python
from arvel.lock.contracts import LockContract

lock = await container.resolve(LockContract)
acquired = await lock.acquire("resource:42", ttl=30)
if acquired:
    try:
        await do_exclusive_work()
    finally:
        await lock.release("resource:42")
```

---

## Mail & Notifications

### Mail

```python
from arvel.mail.contracts import MailContract
from arvel.mail.mailable import Mailable, Attachment

class WelcomeEmail(Mailable):
    template = "welcome"
    subject = "Welcome to the platform"

    def __init__(self, user: User):
        self.to = user.email
        self.context = {"name": user.name}

class InvoiceMail(Mailable):
    template = "invoice"

    def __init__(self, invoice):
        self.to = invoice.customer_email
        self.attachments = [
            Attachment(filename="invoice.pdf", content=invoice.pdf_bytes)
        ]

# Send
mailer = await container.resolve(MailContract)
await mailer.send(WelcomeEmail(user))
```

**Drivers:** SMTP, log, null.

### Notifications

Multi-channel notifications:

```python
from arvel.notifications.contracts import NotificationContract

class InvoicePaidNotification:
    def via(self) -> list[str]:
        return ["mail", "database"]

    def to_mail(self, notifiable) -> MailMessage:
        return MailMessage(subject="Invoice Paid", template="invoice-paid")

    def to_database(self, notifiable) -> dict:
        return {"type": "invoice_paid", "invoice_id": self.invoice_id}

# Send
dispatcher = await container.resolve(NotificationContract)
await dispatcher.send(user, InvoicePaidNotification(invoice))
```

**Channels:** mail, database, Slack.

---

## File Storage

```python
from arvel.storage.contracts import StorageContract

storage = await container.resolve(StorageContract)

# Store a file
await storage.put("avatars/user-42.jpg", image_bytes)

# Read a file
data = await storage.get("avatars/user-42.jpg")

# Delete
await storage.delete("avatars/user-42.jpg")

# Check existence
exists = await storage.exists("avatars/user-42.jpg")
```

**Drivers:** local filesystem, S3-compatible (with managed lifecycle), null.

```bash
STORAGE_DRIVER=local
STORAGE_LOCAL_ROOT=storage/app
STORAGE_S3_BUCKET=my-bucket
STORAGE_S3_REGION=us-east-1
```

---

## Search

Full-text search with swappable engines:

```python
from arvel.search import Searchable, SearchManager

class Post(Searchable, ArvelModel):
    __tablename__ = "posts"
    __searchable__ = ["title", "body"]

# Search
manager = await container.resolve(SearchManager)
results = await manager.search(Post, "async python", limit=20)
```

**Drivers:** Meilisearch, Elasticsearch, database (SQL LIKE), collection (in-memory), null.

```bash
SEARCH_DRIVER=meilisearch
SEARCH_MEILISEARCH_URL=http://localhost:7700
SEARCH_MEILISEARCH_KEY=your-api-key
```

---

## Observability

### Structured Logging

```python
from arvel.logging import Log

logger = Log.named("myapp.orders")
logger.info("order.created", order_id=42, amount_cents=999)
logger.warning("payment.retry", order_id=42, attempt=3)
```

Built-in processors:
- `RequestIdProcessor` — attaches `request_id` to every log entry
- `ContextProcessor` — propagates request context
- `RedactProcessor` — redacts sensitive fields (password, token, secret, etc.)

### OpenTelemetry

```bash
OBSERVABILITY_OTEL_ENABLED=true
OBSERVABILITY_OTEL_SERVICE_NAME=my-app
OBSERVABILITY_OTEL_EXPORTER_ENDPOINT=http://otel-collector:4317
```

### Sentry

```bash
OBSERVABILITY_SENTRY_DSN=https://key@sentry.io/project
OBSERVABILITY_SENTRY_TRACES_SAMPLE_RATE=0.1
```

### Health Checks

```python
from arvel.observability import HealthRegistry, HealthCheck, HealthResult, HealthStatus

class DatabaseHealth(HealthCheck):
    name = "database"

    async def check(self) -> HealthResult:
        try:
            await db.execute("SELECT 1")
            return HealthResult(status=HealthStatus.HEALTHY)
        except Exception as e:
            return HealthResult(status=HealthStatus.UNHEALTHY, message=str(e))

registry = HealthRegistry(timeout=5.0)
registry.register(DatabaseHealth())

# CLI: arvel health check
# HTTP: GET /health
```

---

## Security

### Encryption

```python
from arvel.security.encryption import AesEncrypter

encrypter = AesEncrypter(key=app_key)
encrypted = encrypter.encrypt("sensitive data")
decrypted = encrypter.decrypt(encrypted)
```

AES-256-CBC with HMAC for integrity. Payloads are Base64-encoded.

### Hashing

```python
from arvel.security.hashing import BcryptHasher, Argon2Hasher

hasher = BcryptHasher(rounds=12)
# or
hasher = Argon2Hasher(time_cost=3, memory_cost=65536, parallelism=4)

hashed = hasher.make("password")
is_valid = hasher.check("password", hashed)
```

### Rate Limiting

Configurable per-route or global:

```bash
SECURITY_RATE_LIMIT_DEFAULT=60/minute
SECURITY_RATE_LIMIT_AUTH=5/minute
```

### CSRF Protection

Double-submit cookie pattern with `Origin` header validation:

```bash
SECURITY_CSRF_ENABLED=true
SECURITY_CSRF_EXCLUDE_PREFIXES=["/api/"]
```

---

## CLI

The `arvel` CLI covers the full development lifecycle:

| Command | Purpose |
|---------|---------|
| `arvel new <name>` | Scaffold a new project with interactive stack selector |
| `arvel serve` | Start dev server with hot reload |
| `arvel make model\|controller\|service\|...` | Code generators via Jinja2 templates |
| `arvel db migrate` | Run pending migrations |
| `arvel db rollback` | Roll back migrations |
| `arvel db seed` | Run database seeders |
| `arvel db fresh` | Drop + recreate + migrate + seed |
| `arvel db status` | Show migration status |
| `arvel db publish` | Publish framework migration files |
| `arvel queue work` | Start the queue worker |
| `arvel schedule run` | Execute scheduled tasks |
| `arvel route list` | List all registered routes |
| `arvel tinker` | Interactive REPL (IPython) |
| `arvel health` | Run health checks |
| `arvel about` | Display framework and environment info |
| `arvel config show` | Show resolved configuration |
| `arvel up` / `arvel down` | Maintenance mode on/off |

### Project Scaffolding

```bash
# Interactive mode
arvel new my-app

# Preset selection
arvel new my-app --preset minimal    # SQLite, memory, sync
arvel new my-app --preset standard   # Postgres, Redis, SMTP
arvel new my-app --preset full       # Postgres, Redis, TaskIQ, S3, Meilisearch

# Individual flags
arvel new my-app --database postgres --cache redis --queue taskiq
```

### Custom Commands

Drop a Typer app in `app/Console/Commands/` and it's auto-discovered:

```python
# app/Console/Commands/sync.py
import typer

sync_app = typer.Typer()

@sync_app.command("catalog")
def sync_catalog():
    """Sync product catalog from external API."""
    typer.echo("Syncing...")
```

---

## Testing

### Test Client

```python
from arvel.testing import TestClient, TestResponse

async with TestClient(app) as client:
    response: TestResponse = await client.get("/users")
    response.assert_ok()
    response.assert_json_path("data.0.name", "Alice")

    response = await client.post("/users", json={"name": "Bob", "email": "bob@example.com"})
    response.assert_created()
    response.assert_json_path("id", IsUUID(4))
```

### Assertion Methods

| Method | Checks |
|--------|--------|
| `assert_ok()` | Status 200 |
| `assert_created()` | Status 201 |
| `assert_no_content()` | Status 204 |
| `assert_not_found()` | Status 404 |
| `assert_unprocessable()` | Status 422 |
| `assert_status(code)` | Exact status |
| `assert_json_path(path, value)` | Dot-path JSON value |
| `assert_json_structure(keys)` | Required JSON keys |
| `assert_json_missing(path)` | Path doesn't exist |
| `assert_header(name, value)` | Response header |

### Acting As (Auth Testing)

```python
client.acting_as(user_id=42, headers={"X-Role": "admin"})
response = await client.get("/admin/dashboard")
response.assert_ok()
```

### Database Testing

Transaction rollback isolation:

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///test.db")
    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            yield session
            if trans.is_active:
                await trans.rollback()
    await engine.dispose()
```

### DatabaseTestCase

```python
from arvel.testing import DatabaseTestCase

class TestUserCreation(DatabaseTestCase):
    async def test_create_user(self, db_session):
        await self.seed(db_session, UserSeeder)
        await self.assert_database_has(db_session, User, {"email": "alice@test.com"})
        await self.assert_database_count(db_session, User, 1)
```

### Fakes

Every infrastructure contract has a test double:

```python
from arvel.testing import (
    CacheFake, MailFake, QueueFake, StorageFake,
    LockFake, NotificationFake, EventFake, BroadcastFake, MediaFake,
)

# Cache
cache = CacheFake()
await cache.put("key", "value")
cache.assert_put("key")

# Mail
mail = MailFake()
await mail.send(WelcomeEmail(user))
mail.assert_sent_to("alice@example.com")
mail.assert_nothing_sent()  # Fails — we sent one

# Queue
queue = QueueFake()
await queue.push(SendDigest(user_id=42))
queue.assert_pushed(SendDigest)
queue.assert_pushed_with(SendDigest, {"user_id": 42})

# Events
events = EventFake()
await events.dispatch(OrderShipped(order_id=1))
events.assert_dispatched(OrderShipped)
events.assert_dispatched(OrderShipped, predicate=lambda e: e.order_id == 1)

# Storage
storage = StorageFake()
await storage.put("avatars/1.jpg", b"data")
storage.assert_stored("avatars/1.jpg")

# Notifications
notifications = NotificationFake()
notifications.assert_sent_type(InvoicePaidNotification)

# Broadcasting
broadcast = BroadcastFake()
broadcast.assert_broadcast("order.status.changed")

# Locks
lock = LockFake()
await lock.acquire("resource:42")
lock.assert_acquired("resource:42")
```

---

## Configuration Reference

All configuration uses Pydantic settings with environment variable prefixes:

### Application (`APP_*`)

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `"Arvel"` | Application name |
| `APP_ENV` | `"development"` | Environment (local, staging, production) |
| `APP_DEBUG` | `false` | Debug mode |
| `APP_KEY` | `""` | Encryption key (SecretStr) |
| `APP_DESCRIPTION` | `""` | OpenAPI description |
| `APP_VERSION` | Auto-detected | Application version |

### Database (`DB_*`)

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_URL` | — | Full async database URL |
| `DB_DRIVER` | `"sqlite+aiosqlite"` | Database driver |
| `DB_HOST` | `"localhost"` | Database host |
| `DB_PORT` | `5432` | Database port |
| `DB_DATABASE` | `"arvel"` | Database name |
| `DB_USERNAME` | `""` | Database user |
| `DB_PASSWORD` | `""` | Database password (SecretStr) |

### Cache (`CACHE_*`)

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_DRIVER` | `"memory"` | Driver: memory, redis, null |
| `CACHE_PREFIX` | `""` | Key prefix |
| `CACHE_DEFAULT_TTL` | `3600` | Default TTL in seconds |
| `CACHE_REDIS_URL` | `"redis://localhost:6379/0"` | Redis connection |

### Queue (`QUEUE_*`)

| Variable | Default | Description |
|----------|---------|-------------|
| `QUEUE_DRIVER` | `"sync"` | Driver: sync, null, taskiq |
| `QUEUE_DEFAULT` | `"default"` | Default queue name |
| `QUEUE_REDIS_URL` | `"redis://localhost:6379"` | Redis URL for TaskIQ |
| `QUEUE_TASKIQ_BROKER` | `"redis"` | TaskIQ broker type |

### Mail (`MAIL_*`)

| Variable | Default | Description |
|----------|---------|-------------|
| `MAIL_DRIVER` | `"log"` | Driver: smtp, log, null |
| `MAIL_FROM_ADDRESS` | `"noreply@localhost"` | Sender address |
| `MAIL_FROM_NAME` | `"Arvel"` | Sender name |
| `MAIL_SMTP_HOST` | `"localhost"` | SMTP server |
| `MAIL_SMTP_PORT` | `587` | SMTP port |
| `MAIL_SMTP_USE_TLS` | `true` | Enable TLS |

### Storage (`STORAGE_*`)

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_DRIVER` | `"local"` | Driver: local, s3, null |
| `STORAGE_LOCAL_ROOT` | `"storage/app"` | Local storage path |
| `STORAGE_S3_BUCKET` | `""` | S3 bucket name |
| `STORAGE_S3_REGION` | `"us-east-1"` | S3 region |

### Search (`SEARCH_*`)

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARCH_DRIVER` | `"null"` | Driver: null, collection, database, meilisearch, elasticsearch |
| `SEARCH_MEILISEARCH_URL` | `"http://localhost:7700"` | Meilisearch URL |
| `SEARCH_ELASTICSEARCH_HOSTS` | `"http://localhost:9200"` | Elasticsearch hosts |

### Security (`SECURITY_*`)

| Variable | Default | Description |
|----------|---------|-------------|
| `SECURITY_HASH_DRIVER` | `"bcrypt"` | Hash driver: bcrypt, argon2 |
| `SECURITY_BCRYPT_ROUNDS` | `12` | Bcrypt cost |
| `SECURITY_JWT_ALGORITHM` | `"HS256"` | JWT algorithm |
| `SECURITY_JWT_ACCESS_TTL_MINUTES` | `60` | Access token TTL |
| `SECURITY_JWT_REFRESH_TTL_DAYS` | `30` | Refresh token TTL |
| `SECURITY_CSRF_ENABLED` | `true` | CSRF protection |
| `SECURITY_RATE_LIMIT_DEFAULT` | `"60/minute"` | Default rate limit |
| `SECURITY_RATE_LIMIT_AUTH` | `"5/minute"` | Auth endpoint rate limit |

### Observability (`OBSERVABILITY_*`)

| Variable | Default | Description |
|----------|---------|-------------|
| `OBSERVABILITY_LOG_LEVEL` | `"info"` | Log level |
| `OBSERVABILITY_LOG_FORMAT` | `"auto"` | Format: auto, json, console |
| `OBSERVABILITY_OTEL_ENABLED` | `false` | OpenTelemetry enabled |
| `OBSERVABILITY_SENTRY_DSN` | `""` | Sentry DSN |
| `OBSERVABILITY_ACCESS_LOG_ENABLED` | `true` | Access log middleware |
| `OBSERVABILITY_HEALTH_TIMEOUT` | `5.0` | Health check timeout |

### Session (`SESSION_*`)

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_DRIVER` | `"memory"` | Session driver |
| `SESSION_LIFETIME` | `120` | Session lifetime (minutes) |
| `SESSION_COOKIE` | `"arvel_session"` | Cookie name |
| `SESSION_SECURE` | `false` | Secure cookie flag |
| `SESSION_SAME_SITE` | `"lax"` | SameSite attribute |

### Broadcasting (`BROADCAST_*`)

| Variable | Default | Description |
|----------|---------|-------------|
| `BROADCAST_DRIVER` | `"null"` | Driver: null, redis, memory, log |
| `BROADCAST_REDIS_URL` | `"redis://localhost:6379/0"` | Redis connection |

### Notifications (`NOTIFICATION_*`)

| Variable | Default | Description |
|----------|---------|-------------|
| `NOTIFICATION_DEFAULT_CHANNELS` | `["mail"]` | Default notification channels |
| `NOTIFICATION_SLACK_WEBHOOK_URL` | `""` | Slack webhook URL |
| `NOTIFICATION_DATABASE_TABLE` | `"notifications"` | Database table name |

---

## Project Structure

A scaffolded Arvel project follows this layout:

```
my-app/
├── .env                          # Environment variables
├── bootstrap/
│   └── providers.py              # Service provider registration
├── config/                       # Module configuration overrides
│   ├── app.py                    # AppSettings overrides
│   ├── database.py               # DatabaseSettings
│   ├── cache.py                  # CacheSettings
│   ├── mail.py                   # MailSettings
│   ├── queue.py                  # QueueSettings
│   └── ...
├── app/
│   ├── Models/                   # ArvelModel subclasses
│   ├── Repositories/             # Repository subclasses
│   ├── Services/                 # Business logic services
│   ├── Http/
│   │   ├── Controllers/          # Controller classes
│   │   ├── Middleware/           # Custom middleware
│   │   └── Requests/            # FormRequest validation
│   ├── Events/                   # Event classes
│   ├── Listeners/                # Event listeners
│   ├── Jobs/                     # Queue jobs
│   ├── Mail/                     # Mailable classes
│   ├── Notifications/            # Notification classes
│   ├── Observers/                # Model observers
│   ├── Policies/                 # Authorization policies
│   └── Console/
│       └── Commands/             # Custom CLI commands
├── routes/
│   ├── web.py                    # Web routes
│   └── api.py                    # API routes
├── database/
│   ├── migrations/               # Alembic migrations
│   └── seeders/                  # Database seeders
├── resources/
│   └── lang/                     # Translation files (JSON)
├── storage/
│   ├── app/                      # Application files
│   └── logs/                     # Log files
├── templates/
│   └── mail/                     # Email templates (Jinja2)
├── tests/                        # Test suite
└── docker-compose.yml            # Docker services
```

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **HTTP** | FastAPI + Starlette + Uvicorn | >= 0.135 |
| **ORM** | SQLAlchemy 2.0 (async) | >= 2.0.49 |
| **Migrations** | Alembic | >= 1.18 |
| **Validation** | Pydantic + pydantic-settings | >= 2.12 |
| **CLI** | Typer | >= 0.24 |
| **Logging** | structlog | >= 25.5 |
| **Serialization** | orjson | >= 3.11 |
| **Auth** | PyJWT + bcrypt | >= 2.12 / >= 5.0 |
| **Build** | Hatchling | latest |
| **Lint** | Ruff | >= 0.15 |
| **Type Check** | ty | >= 0.0.27 |
| **Tests** | pytest + anyio | >= 9.0 |
| **Python** | CPython | >= 3.14 |

### Optional Extras

| Extra | Package | Purpose |
|-------|---------|---------|
| `sqlite` | aiosqlite | Async SQLite |
| `pg` | asyncpg | PostgreSQL |
| `mysql` | asyncmy + pymysql | MySQL/MariaDB |
| `redis` | redis[hiredis] | Cache, lock, broadcasting, queue broker |
| `smtp` | aiosmtplib | SMTP mail |
| `s3` | aiobotocore | S3-compatible storage |
| `media` | Pillow | Image processing |
| `argon2` | argon2-cffi | Argon2 password hashing |
| `meilisearch` | meilisearch-python-sdk | Meilisearch search engine |
| `elasticsearch` | elasticsearch[async] | Elasticsearch search engine |
| `taskiq` | taskiq + taskiq-redis | Background task processing |
| `otel` | opentelemetry-* | Distributed tracing |
| `sentry` | sentry-sdk[fastapi] | Error tracking |

---

## Development

### Setup

```bash
git clone https://github.com/Mohamed-Rekiba/arvel.git
cd arvel
uv sync --all-extras
uv run pre-commit install
```

### Commands

```bash
make test-unit       # Unit tests (no Docker)
make test            # Full test suite
make test-docker     # Tests against Docker services
make coverage        # Coverage report
make lint            # Ruff check + format
make typecheck       # ty type checker
make verify          # lint + typecheck + test
make format          # Auto-format
make docs-serve      # Live-reload docs at localhost:8001
make docs-build      # Build docs site (strict mode)
```

### CI/CD

- **CI workflow**: Lint → typecheck → test matrix (SQLite, PostgreSQL, MariaDB)
- **Docs workflow**: Build and deploy MkDocs to GitHub Pages
- **Release workflow**: Automated releases via Release Please
- **Pre-commit**: Ruff, ty, gitleaks, standard hooks
- **Dependabot**: Automated dependency updates

---

*This documentation was generated for Arvel v0.1.5. For the latest information, see the [MkDocs site](https://mohamed-rekiba.github.io/arvel/) and [GitHub repository](https://github.com/Mohamed-Rekiba/arvel).*
