# Release Notes

Arvel follows **Semantic Versioning** (SemVer): `MAJOR.MINOR.PATCH`. Bump the major version when we ship incompatible API changes; minor versions add backward-compatible features; patch versions are fixes that do not change the public contract in a breaking way. That lets you pin versions with confidence and read the changelog when you bump.

The full history lives next to the code: use the GitHub release pages and the repository changelog for every tag, commit references, and grouped changes (features, fixes, and so on).

- [Releases on GitHub](https://github.com/mohamed-rekiba/arvel/releases)
- [CHANGELOG.md](https://github.com/mohamed-rekiba/arvel/blob/main/CHANGELOG.md) in the main branch

## Current release — v0.1.0

The inaugural release of Arvel. Everything is new, so there's no migration path — just install and go.

**Highlights:**

- **HTTP routing** — Laravel-style `Router` with named routes, groups, middleware, and full FastAPI/OpenAPI underneath
- **ORM & data layer** — SQLAlchemy 2.0 async with typed models (`Mapped[T]`), repositories, query builder, relationships, scopes, soft deletes, observers, and migrations via Alembic
- **Dependency injection** — A real container with scopes (app, request, session), providers, and auto-wiring
- **Authentication** — JWT guards, OAuth2/OIDC, bcrypt/argon2 hashing, password reset, email verification, and audit logging
- **Pydantic everywhere** — Request validation, response schemas, application settings, and serialization all flow through Pydantic for end-to-end type safety
- **CLI** — `arvel` commands for scaffolding, serving, database work, queues, scheduling, routes, health checks, tinker REPL, and more (Typer)
- **Mail & notifications** — SMTP driver, database and Slack channels, broadcasting with Redis/memory drivers
- **Queue & scheduler** — Background jobs via TaskIQ with batching, chaining, retries, and cron-based scheduling
- **Cache, sessions & locks** — Pluggable drivers (Redis, memory, null) for caching, session management, and distributed locks
- **File storage** — Local and S3-compatible drivers with managed lifecycle
- **Search** — Meilisearch and Elasticsearch integration via searchable model mixin
- **Media** — Polymorphic file attachments with image handling (Pillow)
- **Observability** — structlog logging, OpenTelemetry instrumentation, Sentry integration, access logs, and health checks
- **Security** — AES encryption, rate limiting, CSRF protection, and security headers
- **Testing** — `TestClient`, `ModelFactory`, and fakes for cache, mail, queue, storage, notifications, media, broadcasting, and locks
- **Documentation** — Full MkDocs Material site covering getting started, architecture, basics, ORM, database, and advanced topics
- **CI/CD** — GitHub Actions for lint, typecheck, test matrix (SQLite/Postgres/MariaDB), docs, and releases; pre-commit hooks with Ruff, ty, and gitleaks

See the [CHANGELOG](https://github.com/mohamed-rekiba/arvel/blob/main/CHANGELOG.md) for the complete list.

## Check which version you have installed

```python
from importlib import metadata

print(metadata.version("arvel"))
```

Run that in your project environment after upgrading to confirm pip or uv resolved the tag you expect.
