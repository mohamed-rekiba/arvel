# Glossary

One term per concept, as used throughout these docs.

| Term | Meaning |
|---|---|
| **Application** | The composition root (`arvel.application.Application`). Holds the container, owns the provider chain, and drives boot/shutdown. |
| **ApplicationBuilder** | Fluent builder (`Application.configure(...)`) that stages config dir, providers, and route files, then `.create()`s a registered (not yet booted) `Application`. |
| **Service container** | The DI core. Binds abstractions to concretes and resolves them with autowiring and scopes. |
| **Binding** | A registered mapping from a key (type) to a factory/concrete, with a lifetime. |
| **Scope** | A binding lifetime: `TRANSIENT` (new each time), `SINGLETON` (one per app), `SCOPED` (one per scope, e.g. request), or a prebuilt `instance`. |
| **Autowiring** | Resolving a class's `__init__` dependencies from their type hints. |
| **Service provider** | A unit that wires a subsystem: `register()` (sync, bindings only), `boot()` (async, I/O), `shutdown()` (async, reverse order). |
| **Baseline providers** | Framework providers pinned at the HEAD/TAIL of the chain (e.g. config, lang, observability at HEAD; console at TAIL). |
| **Facade** | A thin, process-wide static accessor (`Config`, `Auth`, `Bus`, `Mail`, …). A class with a `ClassVar` slot and `@classmethod` delegates — no dynamic proxying. |
| **Config (class-based)** | An `ArvelSettings` subclass resolved via `Config.of(Cls)`. Env-prefix derived from the class name. |
| **config() / lookup()** | Module-based dotted-key config (`config("app.name")`) backed by files in the config dir. |
| **Manager** | A driver factory for a subsystem (`CacheManager`, `QueueManager`, …). Selects a driver from config and caches it. |
| **Driver / store / disk / engine** | A concrete backend implementing a subsystem's `Protocol` (e.g. cache store, storage disk, search engine). |
| **Model** | Arvent ORM base — SQLAlchemy `DeclarativeBase` + `MappedAsDataclass` + `ActiveRecord` + the `ModelMeta` metaclass for clean syntax. |
| **ActiveRecord** | The Eloquent-style CRUD/query surface mixed into `Model`. |
| **QueryBuilder** | Immutable, fluent builder producing a SQLAlchemy `Select`; runs against the active-session `ContextVar`. |
| **Blueprint / Schema** | The migration DSL. `Schema.create/table` drives a `Blueprint` that emits Alembic ops. |
| **Migrator** | Runs `async def up/down` migrations over the Alembic `op` proxy. |
| **Cast** | Type coercion — column-level (`TypeDecorator`) at the DB boundary, or attribute-level (`__casts__`) Python-side. |
| **FormRequest** | A wrapper combining Pydantic parsing (layer 1) with Laravel-style rule validation + `authorize()` (layer 2). |
| **JsonResource / ResourceCollection** | Response shapers that turn models/collections into JSON, with conditional fields and wrapping. |
| **dep()** | Bridges a container binding into a FastAPI `Depends(...)`. |
| **Job** | A queued unit of work (Pydantic, auto-registered). Dispatched via the `Bus` facade. |
| **Worker** | Pops and runs jobs, with retries, backoff, and a dead-letter queue. |
| **Event / Listener** | Pub/sub: `Event.dispatch(event)` fans out to listeners, inline or queued (`ShouldQueue`). |
| **Broadcaster / Reverb** | Publishing side (drivers: log/null/redis-pubsub/pusher) vs. the in-process Pusher-protocol WebSocket server. |
| **Mailable / Notification** | A renderable email; a multi-channel message (mail/database/broadcast/log). |
| **Guard / Gate** | Per-request identity (`AuthManager` guards) vs. authorization (abilities + policies). |
| **Encrypter / Crypt** | AES-256-GCM with a key derived from `APP_KEY` via HKDF; `Crypt` is the env-resolved facade. |
| **Skeleton** | The packaged project template under `_skeleton/`, rendered by `arvel new`. |
| **HEAD / TAIL** | The fixed front/back segments of the provider chain around user/package providers. |
