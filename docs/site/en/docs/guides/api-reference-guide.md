# API Reference Guide

Complete reference for all public modules, classes, and functions in the Arvel framework.

---

## Foundation (`arvel.foundation`)

### `Application`

The ASGI application kernel. Entry point for every Arvel app.

```python
from arvel.foundation import Application
```

| Method | Signature | Description |
|--------|-----------|-------------|
| `configure` | `(base_path: str \| Path, *, testing: bool = False) -> Application` | Sync factory — returns ASGI app, lazy-boots on first request |
| `create` | `async (base_path: str \| Path, *, testing: bool = False) -> Application` | Async factory — eagerly bootstraps. Use for tests/scripts |
| `asgi_app` | `() -> FastAPI` | Returns the underlying FastAPI instance |
| `settings` | `(settings_type: type[T]) -> T` | Returns a typed settings slice |
| `shutdown` | `async () -> None` | Graceful shutdown — reverse provider order |
| `__call__` | `async (scope, receive, send) -> None` | ASGI interface |

### `Container`

DI container with scoped resolution.

```python
from arvel.foundation import Container, Scope
```

| Method | Signature | Description |
|--------|-----------|-------------|
| `resolve` | `async (interface: type[T]) -> T` | Resolve a dependency by type |
| `enter_scope` | `async (scope: Scope) -> Container` | Create a child container |
| `instance` | `(interface: type[T], value: T) -> None` | Register a pre-built instance (post-boot) |
| `close` | `async () -> None` | Close container and clear instances |

### `ContainerBuilder`

Collects bindings during the `register()` phase.

| Method | Signature | Description |
|--------|-----------|-------------|
| `provide` | `(interface: type[T], concrete: type[T], scope: Scope) -> None` | Bind interface to concrete class |
| `provide_factory` | `(interface: type[T], factory: Callable[[], T], scope: Scope) -> None` | Bind interface to factory |
| `provide_value` | `(interface: type[T], value: T, scope: Scope) -> None` | Bind interface to pre-built value |
| `build` | `() -> Container` | Freeze bindings into a Container |

### `Scope`

```python
from arvel.foundation import Scope
```

| Value | Lifetime |
|-------|----------|
| `Scope.APP` | Application singleton |
| `Scope.REQUEST` | Per HTTP request |
| `Scope.SESSION` | Per user session |

### `ServiceProvider`

Base class for module providers.

| Method | Signature | Description |
|--------|-----------|-------------|
| `configure` | `(config: AppSettings) -> None` | Capture config (sync) |
| `register` | `async (container: ContainerBuilder) -> None` | Declare DI bindings |
| `boot` | `async (app: Application) -> None` | Late-stage wiring |
| `shutdown` | `async (app: Application) -> None` | Release resources |

Attribute: `priority: int = 50` (lower boots first)

### `Pipeline`

Ordered pipe processing for middleware and workflows.

| Method | Signature | Description |
|--------|-----------|-------------|
| `send` | `(passable: Any) -> Self` | Set the passable object |
| `through` | `(pipes: list[PipeSpec]) -> Self` | Set the pipe chain |
| `then` | `async (destination: Callable) -> Any` | Execute pipeline with final handler |
| `then_return` | `async () -> Any` | Execute pipeline, return passable |

---

## HTTP (`arvel.http`)

### `Router`

Laravel-style route registration.

```python
from arvel.http import Router
```

| Method | Signature | Description |
|--------|-----------|-------------|
| `get` | `(path, endpoint, *, name, middleware, ...)` | Register GET route |
| `post` | `(path, endpoint, *, name, middleware, ...)` | Register POST route |
| `put` | `(path, endpoint, *, name, middleware, ...)` | Register PUT route |
| `patch` | `(path, endpoint, *, name, middleware, ...)` | Register PATCH route |
| `delete` | `(path, endpoint, *, name, middleware, ...)` | Register DELETE route |
| `resource` | `(prefix, controller_cls)` | Register all CRUD routes |
| `controller` | `(controller_cls)` | Register controller with decorated routes |
| `group` | `(prefix, middleware, ...)` | Context manager for route groups |
| `url_for` | `(name, **params) -> str` | Generate URL by route name |

### `BaseController`

```python
from arvel.http import BaseController, route, Inject
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `prefix` | `str` | URL prefix for all routes |
| `tags` | `tuple[str, ...]` | OpenAPI tags |
| `description` | `str \| None` | Controller description |
| `middleware` | `tuple[str, ...]` | Middleware aliases |

### `route` Decorator Factory

| Method | Creates |
|--------|---------|
| `route.get(path, ...)` | GET route |
| `route.post(path, ...)` | POST route |
| `route.put(path, ...)` | PUT route |
| `route.patch(path, ...)` | PATCH route |
| `route.delete(path, ...)` | DELETE route |

### `Inject(interface: type[T]) -> T`

Resolve a dependency from the request-scoped DI container. Use as a default value in controller method signatures.

### `HttpKernel`

Orchestrates the global middleware stack.

| Method | Description |
|--------|-------------|
| `add_global_middleware(cls, *, priority=50)` | Register middleware class |
| `sorted_middleware()` | Return sorted middleware list |
| `mount(app)` | Register middleware on FastAPI/Starlette |

### `MiddlewareStack`

Resolves middleware aliases to concrete classes.

| Method | Description |
|--------|-------------|
| `expand(names)` | Expand group names to aliases |
| `resolve(names)` | Resolve aliases to classes |

### `JsonResource[T]`

Model-to-response transformation.

| Method | Description |
|--------|-------------|
| `to_dict(instance: T) -> dict` | Transform a single model |
| `to_response() -> dict` | Wrap in response format |

### `ResourceCollection[T]`

Batch model transformation with pagination.

### Response Helpers

| Function | Description |
|----------|-------------|
| `json_response(data, status=200)` | JSON response |
| `no_content()` | 204 No Content |
| `redirect(url, status=302)` | Redirect response |

### Re-exports from FastAPI

`Depends`, `File`, `Form`, `HTTPException`, `Path`, `Query`, `UploadFile`, `status`, `Request`, `Response`, `JSONResponse`

---

## Data Layer (`arvel.data`)

### `ArvelModel`

SQLAlchemy DeclarativeBase with auto-generated Pydantic schema.

| Class Attribute | Type | Description |
|----------------|------|-------------|
| `__tablename__` | `str` | Table name (required) |
| `__fillable__` | `set[str]` | Mass-assignable fields |
| `__guarded__` | `set[str]` | Protected fields |
| `__casts__` | `dict[str, str]` | Type casts |
| `__appends__` | `tuple[str, ...]` | Appended attributes |
| `__global_scopes__` | `list[type[GlobalScope]]` | Global query scopes |
| `created_at` | `Mapped[datetime]` | Auto-managed timestamp |
| `updated_at` | `Mapped[datetime]` | Auto-managed timestamp |

| Method | Signature | Description |
|--------|-----------|-------------|
| `query` | `(session) -> QueryBuilder[Self]` | Create a query builder |
| `model_validate` | `(data: dict) -> Self` | Validate and create from dict |
| `model_dump` | `() -> dict` | Serialize to dict |

### `QueryBuilder[T]`

Fluent query builder over SQLAlchemy `select()`.

| Method | Returns | Description |
|--------|---------|-------------|
| `where(*criteria)` | `Self` | Add WHERE clauses |
| `order_by(*columns)` | `Self` | Add ORDER BY |
| `limit(n)` | `Self` | Set LIMIT |
| `offset(n)` | `Self` | Set OFFSET |
| `with_(*relations)` | `Self` | Eager-load relationships (dot paths) |
| `has(relation, op, count)` | `Self` | Filter by relationship existence |
| `doesnt_have(relation)` | `Self` | Filter by relationship absence |
| `where_has(relation, callback)` | `Self` | Filter by related model conditions |
| `with_count(*relations)` | `Self` | Add subquery counts |
| `all()` | `list[T]` | Execute and return all results |
| `all_with_counts()` | `list[WithCount[T]]` | Execute with count data |
| `first()` | `T \| None` | First result or None |
| `count()` | `int` | Count matching rows |
| `recursive(parent_col, root_id, max_depth)` | `Self` | Recursive CTE query |
| `ancestors(root_id, parent_col)` | `Self` | Find ancestors |
| `descendants(root_id, parent_col)` | `Self` | Find descendants |
| `to_sql()` | `str` | Debug: compiled SQL string |
| `without_global_scope(name)` | `Self` | Exclude a global scope |
| `without_global_scopes()` | `Self` | Exclude all global scopes |

### `Repository[T]`

Generic typed repository with CRUD.

| Method | Signature | Description |
|--------|-----------|-------------|
| `create` | `async (data: dict) -> T` | Create and persist |
| `find` | `async (id) -> T \| None` | Find by primary key |
| `find_or_fail` | `async (id) -> T` | Find or raise `NotFoundError` |
| `update` | `async (instance: T, data: dict) -> T` | Update fields |
| `delete` | `async (instance: T) -> bool` | Delete (soft if mixin present) |
| `restore` | `async (instance: T) -> T` | Restore soft-deleted |
| `force_delete` | `async (instance: T) -> bool` | Permanent delete |
| `query` | `() -> QueryBuilder[T]` | Get query builder |

### `Transaction`

Wraps a session with repository access.

| Method | Description |
|--------|-------------|
| `nested()` | Create a savepoint (context manager) |

### Relationships

```python
from arvel.data.relationships import has_one, has_many, belongs_to, belongs_to_many
from arvel.data.relationships import morph_to, morph_many, morph_to_many
from arvel.data.relationships import register_morph_type
```

### `ModelObserver[T]`

Lifecycle hooks for model events.

| Hook | Phase | Return |
|------|-------|--------|
| `creating(instance)` | Before create | `bool` (False aborts) |
| `created(instance)` | After create | `None` |
| `updating(instance)` | Before update | `bool` (False aborts) |
| `updated(instance)` | After update | `None` |
| `saving(instance)` | Before create/update | `bool` (False aborts) |
| `saved(instance)` | After create/update | `None` |
| `deleting(instance)` | Before delete | `bool` (False aborts) |
| `deleted(instance)` | After delete | `None` |

### `ArvelCollection`

Chainable collection operations.

| Method | Description |
|--------|-------------|
| `map(fn)` | Transform each item |
| `flat_map(fn)` | Transform and flatten |
| `filter(fn)` | Keep matching items |
| `reject(fn)` | Remove matching items |
| `each(fn)` | Side-effect on each item |
| `pluck(key)` | Extract a single field |
| `first()` | First item |
| `last()` | Last item |
| `first_where(key, value)` | First matching item |
| `group_by(key)` | Group by field |
| `chunk(size)` | Split into chunks |
| `sort_by(key)` | Sort by field |
| `unique(key)` | Deduplicate by field |

### `ModelFactory[T]`

Test data generation powered by polyfactory.

| Method | Description |
|--------|-------------|
| `defaults()` | Default attribute values (classmethod) |
| `make(**overrides)` | In-memory instance |
| `create(session, **overrides)` | Persisted instance |
| `create_many(count, session)` | Batch creation |
| `state(name)` | Apply named state |

### Pagination

| Class | Description |
|-------|-------------|
| `PaginatedResult` | Offset-based pagination wrapper |
| `CursorResult` | Cursor-based pagination wrapper |

| Function | Description |
|----------|-------------|
| `encode_cursor(column, value)` | Encode a cursor value |
| `decode_cursor(cursor)` | Decode a cursor value |

### Scopes

| Decorator/Class | Description |
|----------------|-------------|
| `@scope` | Mark a static method as a local scope |
| `GlobalScope` | Base class for global query scopes |

### Soft Deletes

| Mixin | Description |
|-------|-------------|
| `SoftDeletes` | Adds `deleted_at` column and soft delete behavior |

Properties: `trashed` (bool)
Query methods: `with_trashed()`, `only_trashed()`

### Exceptions

| Exception | Description |
|-----------|-------------|
| `NotFoundError` | Model not found |
| `CreationAbortedError` | Observer aborted creation |
| `UpdateAbortedError` | Observer aborted update |
| `DeletionAbortedError` | Observer aborted deletion |
| `ConfigurationError` | Model misconfiguration |

---

## Authentication (`arvel.auth`)

| Class | Description |
|-------|-------------|
| `AuthManager` | Guard management and authentication |
| `JwtGuard` | JWT access/refresh token guard |
| `ApiKeyGuard` | API key authentication |
| `OAuthProviderRegistry` | OAuth2/OIDC provider management |
| `AuthSettings` | Auth configuration |

---

## Validation (`arvel.validation`)

| Class | Description |
|-------|-------------|
| `FormRequest` | Request validation with rules and authorization |
| `Validator` | Standalone validator |
| `Rule` | Base sync rule |
| `AsyncRule` | Base async rule |
| `Exists` | Database existence rule |
| `Unique` | Database uniqueness rule |
| `RequiredIf` | Conditional required |
| `RequiredUnless` | Required unless condition |
| `RequiredWith` | Required with other field |
| `ProhibitedIf` | Prohibited under condition |
| `ConditionalRule` | Base conditional rule |
| `ValidationError` | Validation failure |
| `FieldError` | Single field error |

---

## Events (`arvel.events`)

| Class | Description |
|-------|-------------|
| `Event` | Base event (Pydantic model) |
| `Listener` | Base event listener |
| `EventDispatcher` | Event dispatch and listener registry |

| Decorator | Description |
|-----------|-------------|
| `@queued` | Mark a listener for async queue dispatch |

---

## Broadcasting (`arvel.broadcasting`)

| Class | Description |
|-------|-------------|
| `BroadcastContract` | Broadcasting interface |
| `Broadcastable` | Mixin for broadcastable events |
| `Channel` | Public channel |
| `PrivateChannel` | Private (authenticated) channel |
| `PresenceChannel` | Presence channel |
| `ChannelAuthorizer` | Channel authorization |
| `BroadcastEventListener` | Auto-broadcast listener |
| `BroadcastSettings` | Configuration |
| `RedisBroadcaster` | Redis driver |

---

## Queue (`arvel.queue`)

| Class | Description |
|-------|-------------|
| `Job` | Base job (Pydantic model) |
| `QueueContract` | Queue interface |
| `QueueManager` | Driver management |
| `Batch` | Job batch processing |
| `Chain` | Sequential job chain |
| `JobRunner` | Worker loop |
| `JobMiddleware` | Base job middleware |
| `RateLimited` | Rate limit middleware |
| `WithoutOverlapping` | Prevent concurrent execution |
| `UniqueJobGuard` | Unique job enforcement |
| `QueueSettings` | Configuration |

---

## Cache (`arvel.cache`)

| Interface | Description |
|-----------|-------------|
| `CacheContract` | Cache operations |

| Method | Signature |
|--------|-----------|
| `get` | `async (key: str) -> Any \| None` |
| `put` | `async (key: str, value: Any, ttl: int) -> None` |
| `forget` | `async (key: str) -> None` |
| `has` | `async (key: str) -> bool` |
| `flush` | `async () -> None` |
| `remember` | `async (key: str, ttl: int, callback: Callable) -> Any` |

Drivers: `memory`, `redis`, `null`

---

## Lock (`arvel.lock`)

| Interface | Description |
|-----------|-------------|
| `LockContract` | Distributed lock operations |

| Method | Signature |
|--------|-----------|
| `acquire` | `async (name: str, ttl: int) -> bool` |
| `release` | `async (name: str) -> None` |

Drivers: `memory`, `redis`, `null`

---

## Mail (`arvel.mail`)

| Class | Description |
|-------|-------------|
| `MailContract` | Mail sending interface |
| `Mailable` | Email message template |
| `Attachment` | File attachment |
| `MailSettings` | Configuration |

Drivers: `smtp`, `log`, `null`

---

## Notifications (`arvel.notifications`)

| Interface | Description |
|-----------|-------------|
| `NotificationContract` | Multi-channel notification dispatch |

Channels: `mail`, `database`, `slack`

---

## Storage (`arvel.storage`)

| Interface | Description |
|-----------|-------------|
| `StorageContract` | File storage operations |

| Method | Signature |
|--------|-----------|
| `put` | `async (path: str, data: bytes) -> None` |
| `get` | `async (path: str) -> bytes` |
| `delete` | `async (path: str) -> None` |
| `exists` | `async (path: str) -> bool` |

Drivers: `local`, `s3` (managed), `null`

---

## Search (`arvel.search`)

| Class | Description |
|-------|-------------|
| `SearchEngine` | Search engine contract |
| `SearchManager` | Driver management |
| `SearchBuilder` | Fluent search query builder |
| `Searchable` | Model mixin for search indexing |
| `SearchObserver` | Auto-index on model changes |
| `SearchProvider` | DI registration |
| `SearchSettings` | Configuration |

| Result Type | Description |
|-------------|-------------|
| `SearchHit` | Single search result |
| `SearchResult` | Collection of hits |
| `PaginatedSearchResult` | Paginated search results |

Drivers: `meilisearch`, `elasticsearch`, `database`, `collection`, `null`

---

## Observability (`arvel.observability`)

| Class | Description |
|-------|-------------|
| `ObservabilityProvider` | Provider for all observability features |
| `ObservabilitySettings` | Configuration |
| `HealthRegistry` | Health check management |
| `HealthCheck` | Base health check |
| `HealthResult` | Health check result |
| `HealthStatus` | HEALTHY / DEGRADED / UNHEALTHY |
| `AccessLogMiddleware` | Structured access logging |
| `RequestIdMiddleware` | Request ID propagation |

| Function | Description |
|----------|-------------|
| `configure_logging(settings)` | Set up structlog pipeline |
| `configure_tracing(settings)` | Set up OpenTelemetry |
| `configure_sentry(settings)` | Set up Sentry integration |
| `get_request_id()` | Get current request ID |
| `get_tracer()` | Get OpenTelemetry tracer |

### Log Processors

| Processor | Description |
|-----------|-------------|
| `RequestIdProcessor` | Attach request ID to log entries |
| `ContextProcessor` | Propagate request context |
| `RedactProcessor` | Redact sensitive fields |

---

## Security (`arvel.security`)

| Class | Description |
|-------|-------------|
| `BcryptHasher` | Bcrypt password hashing |
| `Argon2Hasher` | Argon2 password hashing |
| `AesEncrypter` | AES-256-CBC encryption |
| `CsrfMiddleware` | CSRF protection |
| `RateLimitMiddleware` | Rate limiting |
| `SecuritySettings` | Configuration |

---

## Context (`arvel.context`)

| Class | Description |
|-------|-------------|
| `Context` | Request-scoped key-value store |
| `Concurrency` | Structured concurrency helpers |
| `ContextMiddleware` | Auto-manage context lifecycle |
| `DeferredTaskMiddleware` | Execute deferred tasks after response |
| `ContextProvider` | DI registration |

| Function | Description |
|----------|-------------|
| `defer(fn)` | Schedule a function to run after the response |

---

## i18n (`arvel.i18n`)

| Class/Function | Description |
|---------------|-------------|
| `Translator` | Locale-aware message resolution |
| `trans(key, *, locale, **params)` | Translate a key |
| `set_translator(t)` | Set global translator |
| `get_translator()` | Get global translator |

---

## Testing (`arvel.testing`)

| Class | Description |
|-------|-------------|
| `TestClient` | Async HTTP test client |
| `TestResponse` | Response with assertion methods |
| `DatabaseTestCase` | Database testing utilities |
| `ModelFactory[T]` | Test data generation |
| `FactoryBuilder` | Factory state builder |

### Fakes

| Fake | Contract |
|------|----------|
| `CacheFake` | `CacheContract` |
| `MailFake` | `MailContract` |
| `QueueFake` | `QueueContract` |
| `StorageFake` | `StorageContract` |
| `LockFake` | `LockContract` |
| `EventFake` | `EventDispatcher` |
| `NotificationFake` | `NotificationContract` |
| `BroadcastFake` | `BroadcastContract` |
| `MediaFake` | `MediaContract` |

Each fake provides assertion methods specific to its domain (e.g., `cache.assert_put(key)`, `mail.assert_sent_to(email)`, `queue.assert_pushed(JobClass)`).

---

## Contracts (`arvel.contracts`)

Convenience re-exports for all infrastructure contracts:

```python
from arvel.contracts import (
    CacheContract,
    LockContract,
    MailContract,
    MediaContract,
    NotificationContract,
    StorageContract,
)
```

---

## Support (`arvel.support`)

| Function | Description |
|----------|-------------|
| `data_get(obj, dotted_path, default)` | Deep dict/object access |
| `to_snake_case(name)` | Convert to snake_case |
| `pluralize(word)` | Simple English pluralization |

---

## Logging (`arvel.logging`)

| Class | Description |
|-------|-------------|
| `Log` | Logging facade |

| Method | Description |
|--------|-------------|
| `Log.named(name)` | Get a named structlog logger |

---

*API reference for Arvel v0.1.5. Auto-generated API docs are also available via `mkdocstrings` in the MkDocs site.*
