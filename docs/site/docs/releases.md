# Release Notes

Arvel is pre-1.0, currently at `v0.3.0`. The core subsystems are complete and working; the public API may still shift before `1.0`. This page covers the versioning scheme, the support policy, and a high-level map of what's in the box. For the full, per-release changelog, see [`CHANGELOG.md`](https://github.com/mohamed-rekiba/arvel/blob/main/CHANGELOG.md).

<a name="versioning-scheme"></a>
## Versioning Scheme

From `1.0.0` onward, Arvel follows [Semantic Versioning](https://semver.org). Until then:

- `0.x.y` releases may introduce breaking changes between minor versions.
- Any breaking change is documented in the [Upgrade Guide](upgrade.md) with before/after examples.
- Each release tags a commit on `main` and publishes an sdist + wheel for `arvel` to PyPI.

<a name="support-policy"></a>
## Support Policy

| Track | Status | Support |
|---|---|---|
| `0.x` | Pre-release | Best-effort; APIs may change |
| `1.x` | Not yet released | Bug fixes + security patches for 18 months after release |
| `main` | Always the tip | No stability guarantees |

<a name="requirements"></a>
## Requirements

Arvel requires **Python 3.14+** — it leans on `Self`, `TaskGroup`, and modern typing. Every public symbol passes `mypy --strict` and `pyright --strict`. Optional features (Redis, Postgres, S3, queues, mail, JWT, broadcasting, …) ship as [extras](getting-started/installation.md); `pip install 'arvel[all]'` pulls everything.

<a name="whats-included"></a>
## What's Included

| Subsystem | Highlights |
|---|---|
| **Application & container** | Async-first boot; typed DI `Container`; `ServiceProvider` lifecycle; facades |
| **HTTP** | `Route` over FastAPI; middleware stack; `FormRequest` validation; `JsonResource` / `ResourceCollection`; uniform error envelope |
| **Arvent ORM** | SQLAlchemy-backed `Model`; relationships; query builder; `Timestamps` / `SoftDeletes`; casts, accessors, observers, scopes; factories & seeders |
| **Migrations** | Alembic-backed `Migrator`; `migrate`, `migrate:rollback`, `migrate:fresh`, `migrate:status` |
| **Console** | `arvel` CLI (Typer); `new`, 25+ `make:*` generators, migration/queue/cache/schedule commands; `shell` REPL; `route:list` |
| **Auth** | JWT access + refresh with rotation; `JwtGuard` / `SessionGuard` / `TokenGuard`; email verification & password reset; login throttling + CSRF double-submit; `auth:install` publishes config/migration/User/route stubs |
| **Authorization** | `Gate`, policies, before-hooks — bound by `AuthServiceProvider` |
| **Cache / Session / Storage** | Driver protocols (Redis, file, array, cookie; local, S3-compatible, GCS, Azure); HMAC-signed temporary URLs |
| **Queues** | `Job` with `delay` / `priority` / `backoff` / `retry_until`; sync, database, redis-direct, and taskiq (Redis + AMQP) drivers; DLQ + retry commands |
| **Events / Mail / Notifications** | Typed events with sync & queued listeners; `Mailable` (`envelope()` / `content()`); notifications over log, mail, database, and broadcast channels |
| **Broadcasting** | `ShouldBroadcast` events on channels via the `redis-pubsub` driver, fanned out by a Pusher-protocol WebSocket server (`arvel reverb:start`, `arvel[broadcasting]` extra) |
| **Scheduling** | Cron DSL; `schedule:work`; auto-registered `SchedulerServiceProvider` |
| **Config / Logging / i18n** | Typed `ArvelSettings` (auto-derived env prefixes); structlog `Log`; locale-negotiated translations |
| **OpenAPI** | `openapi:export` / `openapi:validate` for a generated, validated API contract |
| **Testing** | `ArvelTestCase`, `TestResponse`, pytest fixtures, and `.fake()` helpers (`Cache`, `Event`, `Mail`, `Storage`) |

<a name="companion-packages"></a>
## Companion Packages

Optional packages live in the same monorepo and install as extras (`arvel[oauth]`, `arvel[permission]`, …):

| Package | What it adds |
|---|---|
| [`arvel-oauth`](packages/oauth.md) | OAuth2 / OIDC social login (Google, GitHub, …) |
| [`arvel-permission`](packages/permission.md) | Roles & permissions with `Gate` integration |
| [`arvel-image`](packages/image.md) | Image manipulation + a media library |
| [`arvel-search`](packages/search.md) | Full-text search over models |
| [`arvel-audit`](packages/audit.md) | Model audit trails & activity logs |
| [`arvel-ecommerce-demo`](packages/ecommerce-demo.md) | A full reference app built on Arvel |

<a name="roadmap"></a>
## Roadmap

Unreleased work — recursive tree relations, Laravel-style validation rules, route model binding, resource controllers, and more — is tracked under `[Unreleased]` in [`CHANGELOG.md`](https://github.com/mohamed-rekiba/arvel/blob/main/CHANGELOG.md). The headline goal before `1.0` is a public-API review and stability pass.
