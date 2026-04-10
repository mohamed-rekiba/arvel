# Changelog

All notable changes to Arvel are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4](https://github.com/mohamed-rekiba/arvel/compare/v0.1.3...v0.1.4) (2026-04-10)


### Bug Fixes

* **cli:** include db_password in context for new command ([84b77a2](https://github.com/mohamed-rekiba/arvel/commit/84b77a2f37f9edb6d716b6a29dda8f51b741bc5e))

## [0.1.3](https://github.com/mohamed-rekiba/arvel/compare/v0.1.2...v0.1.3) (2026-04-10)


### Bug Fixes

* **observability:** resolve health checks for project-level settings overrides ([73cbb94](https://github.com/mohamed-rekiba/arvel/commit/73cbb948e50dd8c30398112249b13c505dd6f778))

## [0.1.2](https://github.com/mohamed-rekiba/arvel/compare/v0.1.1...v0.1.2) (2026-04-10)


### Bug Fixes

* **config:** route all provider settings through load_config pipeline ([555ac9c](https://github.com/mohamed-rekiba/arvel/commit/555ac9c6b9e7e8103b12a521dbac0da1e1d6be56))

## 0.1.1 (2026-04-10)


### Features

* **cli:** add interactive stack selector, docker-compose templating, and InquirerPy prompts ([53cf56a](https://github.com/mohamed-rekiba/arvel/commit/53cf56a7569cf438d512eaef49e15ea5e5653c57))

## [Unreleased]

## [0.1.0] - 2026-04-10

Initial release of the Arvel framework — an async-first, type-safe Python web framework inspired by Laravel, built on FastAPI, SQLAlchemy 2.0, and Pydantic.

### Added

#### Core

- Application container with scoped dependency injection, providers, and auto-wiring
- Service provider architecture for modular application bootstrapping
- Pipeline (middleware) pattern for composable request processing
- Application lifecycle management with boot, serve, and shutdown hooks

#### HTTP

- Laravel-style `Router` with named routes, groups, and middleware — full FastAPI/OpenAPI underneath
- `Request` and `Response` wrappers with typed access to headers, query params, and body
- Controller base class with resource routing
- Exception handler with structured JSON error responses
- Signed URL generation and verification
- JSON resource layer for API response transformation
- URL generation helpers

#### ORM & Data Layer

- SQLAlchemy 2.0 async models with `Mapped[T]` and `mapped_column()` throughout
- `ArvelModel` base class with automatic `created_at`/`updated_at` timestamps
- Repository pattern with typed query builder
- Relationship helpers: `has_one`, `has_many`, `belongs_to`, `belongs_to_many`
- Global and local query scopes
- Soft deletes with `trashed()`, `with_trashed()`, `restore()`, and `force_delete()`
- Model observers with lifecycle hooks (`creating`, `created`, `updating`, etc.)
- Collection class with chainable operations
- Cursor-based and offset-based pagination
- Mass assignment protection via `__fillable__` / `__guarded__`
- Transaction management with savepoint (nested) support
- Schema introspection utilities
- Typed query results and accessor support
- Database configuration with connection pooling

#### Migrations & Seeding

- Alembic-based migration management through the CLI
- Database seeder support

#### Authentication & Authorization

- JWT guard with token issuance, refresh, and validation
- OAuth2 / OIDC integration
- Password hashing with bcrypt and optional argon2 support
- Password reset flow
- Email verification middleware
- Audit logging for auth events

#### Validation

- Pydantic-powered request validation
- Custom validation rules
- Form request objects for complex validation logic
- Structured validation error responses

#### CLI

- `arvel serve` — start the dev server with hot reload
- `arvel new project <name>` — scaffold a new project (with `--database` flag)
- `arvel make model|controller|service|listener` — code generators via Jinja2 templates
- `arvel db migrate|seed|fresh` — database management
- `arvel queue work` — start the queue worker
- `arvel schedule run` — execute scheduled tasks
- `arvel route list` — list registered routes
- `arvel tinker` — interactive REPL (IPython)
- `arvel health` — application health check
- `arvel about` — display framework and environment info
- Maintenance mode commands

#### Mail & Notifications

- Mailable class with SMTP driver and null driver for testing
- Notification dispatcher with pluggable channels
- Database notification channel
- Slack notification channel
- Notification migration support
- Mail and notification fakes for testing

#### Events & Broadcasting

- Event dispatcher with listener discovery
- Typed event classes
- Broadcasting with Redis, memory, log, and null drivers
- Broadcasting fakes for testing

#### Queue & Scheduler

- Background job processing via TaskIQ driver
- Job batching and chaining
- Failed job tracking and retry
- Unique job support
- Queue middleware
- Cron-based task scheduling with distributed lock support

#### Cache, Sessions & Locks

- Cache manager with Redis, memory (in-process), and null drivers
- Session management with configurable backends
- Distributed lock contracts with memory driver
- Lock fakes for testing

#### File Storage

- Storage abstraction with local filesystem and S3-compatible drivers
- Managed S3 driver with automatic lifecycle management
- Null driver and fakes for testing

#### Search

- Full-text search integration with Meilisearch and Elasticsearch drivers
- Searchable model mixin
- Search manager for driver resolution

#### Media

- Media model for polymorphic file attachments
- Media mixins for model integration
- Image handling via Pillow (optional extra)
- Media migration support
- Media events and fakes for testing

#### Observability

- Structured logging via structlog with context propagation
- OpenTelemetry instrumentation (traces and spans)
- Sentry integration for error tracking
- Access log middleware
- Health check endpoint

#### Security

- AES encryption helpers
- Rate limiting middleware
- CSRF protection
- Security headers configuration
- Password hashing abstraction

#### Internationalization

- Translator with locale-aware message resolution

#### Context

- Request-scoped context propagation
- Concurrency-safe context middleware

#### Testing

- `TestClient` for async HTTP testing
- `ModelFactory` base class powered by polyfactory
- Fakes for cache, mail, queue, storage, notifications, media, broadcasting, and locks
- Database test utilities with transaction rollback isolation

#### Activity & Audit

- Activity log entries for tracking model changes
- Audit trail with migration support
- Auditable model mixin

#### Infrastructure & Configuration

- `pydantic-settings` for typed application configuration
- `.env` file support via python-dotenv
- Infrastructure provider for service wiring
- Support module with type guards

#### Documentation

- MkDocs Material documentation site with full guide coverage
- Getting started, architecture, basics, ORM, database, and digging-deeper sections
- API reference index

#### DevOps & CI

- GitHub Actions CI workflow (lint, typecheck, test matrix across SQLite/Postgres/MariaDB)
- GitHub Actions docs deployment workflow
- GitHub Actions release workflow
- Dependabot configuration for automated dependency updates
- Pre-commit hooks: Ruff, ty, gitleaks, standard checks
- Dockerfile for containerized deployment
- Docker Compose with Postgres, MariaDB, Valkey, Mailpit, MinIO, Meilisearch, Elasticsearch, and Keycloak
- Makefile with `setup`, `test`, `lint`, `typecheck`, `verify`, `coverage`, `docs-serve`, and more
- `.editorconfig`, `.gitattributes`, and VS Code workspace settings
- Pull request template

[Unreleased]: https://github.com/Mohamed-Rekiba/arvel/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Mohamed-Rekiba/arvel/releases/tag/v0.1.0
