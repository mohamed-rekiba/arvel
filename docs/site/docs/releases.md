# Release Notes

Arvel is in pre-alpha at `v0.3.0`. This page captures what has shipped and what is coming next.

## Versioning Scheme

Once `1.0.0` ships, Arvel will follow [Semantic Versioning](https://semver.org). Until then:

- `0.x.y` releases may include breaking changes between minor versions.
- Breaking changes are called out explicitly in the release notes below.
- Every release tags a commit on `main` and ships sdist + wheel for `arvel` to PyPI.

## Support Policy

| Track | Status | Support |
|---|---|---|
| `0.x` | Pre-release | Best-effort; APIs may change |
| `1.x` | Not yet released | Bug fixes + security patches for 18 months after release |
| `latest` | Always tip of `main` | No stability guarantees |

## What's shipped

### Core framework

- **Application & service container** — typed, async-first `Application` boot sequence; `Container` with dependency injection, `ServiceProvider` base, facades.
- **Routing** — `Route` facade wrapping FastAPI; middleware stack (global, route-scoped); form request validation; typed request/response helpers.
- **Arvent** — `Model` base class on SQLAlchemy; `Timestamps`, `SoftDeletes`, `QueryBuilder[T]`; typed column helpers (`id_`, `string`, `text`, `json`, `foreign_id`, …); schema DSL that compiles to Alembic operations; factories and seeders.
- **Console** — `arvel` CLI (Typer-backed); `make:model`, `make:migration`, `make:schema`, `make:controller`, and 20+ scaffolding generators; `arvel shell` REPL with auto-imported models and facades; `arvel migrate`, `arvel db:seed`; maintenance mode commands.
- **Cache** — driver protocol with Redis, file, array, and null backends; `Cache` facade; version-stamped keys pattern.
- **Sessions** — driver protocol with Redis and cookie backends; `Session` facade.
- **File storage** — `Storage` facade; local, S3-compatible, and public drivers; HMAC-signed temporary URLs.
- **Configuration** — typed `ArvelSettings` (Pydantic `BaseSettings`); `@register` decorator; `Config.fake()` for tests; `config/*.py` bridge pattern for Laravel-shaped config files.
- **Logging** — structlog-backed `Log` facade; JSON and console renderers; request-scoped context propagation.
- **Internationalization** — `Lang` facade; JSON catalog files; locale negotiation middleware; `Translator` with dotted-key lookup and `:placeholder` interpolation.

### Auth

- JWT access + refresh token pair with rotation-by-default; SHA-256 hashed token storage.
- Guards: `JwtGuard`, `SessionGuard`, `TokenGuard`.
- `auth:install` command wires all nine auth endpoints (`/register`, `/login`, `/refresh`, `/logout`, `/me`, `/email/verify`, `/email/resend`, `/forgot-password`, `/reset-password`) in one step.
- Email verification and password-reset flows with Jinja2 mail templates.
- `VerifiedMiddleware`, `AuthMiddleware`, per-route ability checks.

### Queues & background jobs

- `Job` base class with `delay` and `priority` fields.
- Four drivers: sync, database (PostgreSQL), Redis-direct, and AMQP (RabbitMQ via `taskiq-aio-pika`).
- Configurable retry with exponential backoff; dead-letter queue with `arvel queue:failed`, `arvel queue:retry`, `arvel queue:flush` CLI.
- Worker loop with graceful shutdown (`arvel queue:work`).

### Events, mail, notifications, broadcasting

- `Event` facade; typed event classes; sync and queued listeners.
- `Mail` facade; `Mailable` base class; SMTP, log, and array drivers; Jinja2 template rendering.
- `Notification` facade; `Notifiable` mixin; mail and database channels.
- `Broadcast` facade; `ShouldBroadcast` mixin; Pusher-protocol driver (Reverb-compatible); channel authentication.
- `arvel-reverb` WebSocket server (Pusher-compatible, async).

### Database extras

- Encrypted column type (`EncryptedType`); `PydanticType` generic cast; `EmailAddress` value-object column helper.
- Recursive CTEs; savepoints; query logging; `raw_column(...)` escape hatch.
- `Blueprint.jsonb()` — PostgreSQL `JSONB` column that degrades to `JSON` on other dialects; pairs with `t.gin_index()` for containment queries.
- Alembic-backed `Migrator` with `arvel migrate`, `arvel migrate:rollback`, `arvel migrate:fresh`.
- `arvel make:schema` — auto-generates `*Read` / `*Create` / `*Update` Pydantic schemas from a model.

### Packages

- **`arvel-permission`** — Spatie Laravel Permission v7 port; `Role`, `Permission`, `HasRoles`, `HasPermissions`, gate integration, polymorphic pivot tables. Includes query-scope classmethods (`query_with_role`, `query_without_role`, `query_with_permission`, `query_without_permission`), wildcard subparts, an opt-in events system (`RoleAttachedEvent`, `PermissionAttachedEvent`, …), bidirectional `Permission.roles` navigation, pipe-separated OR in route middleware (`role:admin|manager`), and the `UnauthorizedException` hierarchy for structured error handling.
- **`arvel-image`** — Spatie Image v3 port (Pillow-backed, no native deps); fluent `Image` class; plus a full `laravel-medialibrary` v11 port (`Media` model, `HasMedia` / `HasMediaMixin`, collections, conversions, path generator). `attach_media(source, collection=...)` and `delete_media(collection=...)` provide single-call shortcuts over the `add_media(...).to_media_collection(...)` chain.

### Starter kit

- `arvel new` scaffolds an API-first skeleton with auth, migrations, and a `healthz` endpoint ready to go.

## What's next

- Login rate-limiting (429 response).
- `arvel-permission` teams support.
- `mkdocstrings` API reference auto-generation.
- `0.4.0` — public API surface review and stability improvements ahead of `1.0`.
