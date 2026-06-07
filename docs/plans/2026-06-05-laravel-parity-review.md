# Laravel-parity review — 2026-06-05

Aggregated output from a parallel five-agent audit against Laravel's documented
feature surface. Generated during the autonomous review→implement→docs loop.

## Audit scope

| Agent | Subsystem |
|---|---|
| A | `arvel.validation` + `arvel.http.requests` (FormRequest) |
| B | `arvel.routing`, `arvel.http` |
| C | `arvel.database` (ORM, migrations, query builder) |
| D | `arvel.queue`, `arvel.scheduling`, `arvel.events`, `arvel.broadcasting`, `arvel.cache`, `arvel.mail`, `arvel.notifications`, `arvel.storage`, `arvel.reverb` |
| E | `arvel.auth`, `arvel.i18n`, `arvel.testing`, `arvel.config`, `arvel.container`, `arvel.maintenance`, `arvel.encryption`, `arvel.session`, `arvel.support`, + global TODO/FIXME/HACK sweep |

## Parity headline

| Area | Coverage | Notes |
|---|---|---|
| ORM / DB | ~80–85% | Strong: pivot M2M, polymorphism, adjacency CTE trees, soft deletes, scopes, observers, factories, migrations, transactions w/ savepoints + deadlock retry. Async-first surface. |
| Routing / HTTP | ~55% | Routing core, model binding, resources, FormRequest, JsonResource, CSRF, Reverb — all real. Missing: `response()`/`redirect()`/`Http::` facades, route caching, nested/singleton resources, trusted proxies, middleware kernel. |
| Queue / Scheduler / Events | ~45–55% | Sync/db/redis drivers, scheduler DSL, queued listeners, Reverb. Missing: real batch/chain semantics, job middleware, scheduler maintenance/output, SQS/Beanstalk, mailgun/ses. |
| Auth / Authz / i18n / Testing | ~60% | Session/token/JWT guards, password reset, email verification, gates+policies, full Pluralisation. Missing: `Gate` facade, `User::can()`, `RefreshDatabase`, `Queue::fake` parity, remember-me actually wired. |
| Validation | ~15% (6 of 37 string rules) | Strongest gap. Pydantic carries most validation today; Laravel-style `rules()` on `FormRequest` is real but the rule library is thin. |

## Critical bugs (broken behaviour shipping today)

Routed to `docs/backlog/002` and `003`:

1. `Bus.chain` / `Bus.batch` advertise sequential / batch semantics, run fan-out — `arvel.queue.bus`.
2. `queue:work` constructs `Worker` without `QueueRestartSignal`; `queue:restart` is a no-op — `arvel.queue.commands.queue_work` vs `arvel.queue.worker`.
3. `ScheduledTask.in_maintenance_mode` and `.output_to` stored, never read — `arvel.scheduling.scheduled_task` vs `arvel.scheduling.kernel._invoke`.
4. `Seeder.call()` returns instance without running it — `arvel.database.seeders`.
5. `arvent` accepted in `AuthConfig.provider.driver`, raises at runtime — `arvel.auth.provider._build_provider`. (Resolved 2026-06-05 — driver renamed `database` → `arvent`, provider class renamed `DatabaseUserProvider` → `ArventUserProvider`.)
6. `LoginRequest.remember` accepted, never consumed — `arvel.auth.http.requests`.
7. `MaintenanceModeManager.template` written, never read — `arvel.maintenance.middleware`.
8. `ArraySessionStore` implemented, not registered — `arvel.session.manager._create`.
9. `refresh_database()` calls a non-existent helper, silent no-op — `arvel.testing.case`.
10. `EventDispatcher` and `NotificationManager` silently fall back to inline on Bus failure.
11. CSRF header case mismatch (`X-CSRF-Token` vs `X-CSRF-TOKEN`) — `_middleware_core.py` vs `auth/middleware/csrf_double_submit.py`.
12. Duplicate `CsrfMismatchException` classes (same name, two modules).
13. `health.py` and `observability/metrics_route.py` trust first `X-Forwarded-For` hop without an allowlist.
14. Root `CHANGELOG.md [Unreleased]` lists already-shipped items (route model binding, resource controllers, recursive trees).
15. Two `# TODO` stub view migrations in `console/commands/make_migration.py`.

## Top Laravel feature gaps (not bugs)

Routed to planned WIs 004, 005, 006, 008:

- Validation: ~25 missing string rules (`string`, `integer`, `min`, `max`, `in`, `email`, `url`, `date`, `confirmed`, `same`, `different`, `nullable`, `bail`, etc.), conditional rules, nested/wildcard, custom rule extension, `Rule::in()` / `Rule::unique()` builders.
- HTTP: `response()`, `redirect()`, `Http::` facades; `route:cache` / `route:clear`; nested/singleton resource macros; `Route::model` registry; trusted-proxy middleware; middleware kernel with aliases/priority/terminate.
- Test surface: `RefreshDatabase`, `DatabaseTransactions`, `Queue::fake`, `Notification::fake`, `Http::fake`, `Bus::fake`; JSON HTTP helpers (`getJson`/`postJson`/`assertExactJson`).
- Auth UX: `Gate` facade, `User::can()`, `Gate::resource`, policy auto-discovery, `MustVerifyEmail` interface.
- ORM polish: `HasFactory` / `Model::factory()`, custom pivot `using()`, `MorphToMany` pivot ergonomics, table-name inference, `Model::preventLazyLoading()`.
- Messaging: real chain/batch, job middleware (`RateLimited`, `WithoutOverlapping`), unique jobs, encrypted jobs, mailgun/ses/postmark mail drivers, queued/localised mail, SMS/Slack notification channels.

## Iteration plan

| Iter | WI | Scope |
|---|---|---|
| 1 (this) | 002, 003, 007 | Surgical bug fixes + doc freshness |
| 2 | 004, 005 | Test parity + validation rule expansion |
| 3 | 006, 008 | HTTP facades + route caching + security hardening |
| 4 | 001 | Needs-based CLI bootstrap |

## Reference paths (for next iteration)

- Backlog: `docs/backlog/00{1,2,3,7}-epic-*.md`
- Roadmap: `docs/backlog/ROADMAP.md`
- Existing CHANGELOG: `CHANGELOG.md`
- Site docs root: `docs/site/docs/`
