# Source map

Where each subsystem lives in the tree, so a doc page maps back to code. All paths are under `packages/arvel/src/arvel/` unless noted.

## Core

| Area | Path | Docs |
|---|---|---|
| Application / builder | `application/` | [bootstrap](../architecture/bootstrap-lifecycle.md) |
| Service container | `container/` | [container](../architecture/service-container.md) |
| Service providers (base) | `providers/service_provider.py` | [providers](../architecture/service-providers.md) |
| Baseline providers | `providers/` | [providers](../architecture/service-providers.md) |
| Config (class + module) | `config/` | [configuration](../architecture/configuration.md) |
| Facades | `facades/` | [facades](../architecture/facades.md) |
| Support / annotations | `support/` | — |

## HTTP

| Area | Path | Docs |
|---|---|---|
| Routing | `routing.py`, `providers/http_provider.py` | [routing](../http/routing.md) |
| `dep()` | `dep.py` | [routing](../http/routing.md) |
| Middleware | `http/` | [middleware](../http/middleware.md) |
| Form requests / validation | `validation/`, `http/` | [requests & validation](../http/requests-validation.md) |
| JSON resources | `http/` | [resources](../http/resources.md) |
| Exceptions | `http/` | [exceptions](../http/exceptions.md) |

## ORM (Arvent)

| Area | Path | Docs |
|---|---|---|
| Model / ActiveRecord / metaclass | `database/model.py`, `attributes.py`, `columns.py`, `mixins.py` | [model internals](../orm/model-internals.md) |
| Query builder | `database/query.py`, `query_mixin.py`, `collection.py`, `paginator.py`, `scope.py` | [query builder](../orm/query-builder.md) |
| Relationships | `database/orm/` | [relationships](../orm/relationships.md) |
| Casts | `database/casts.py` | [casts](../orm/casts.md) |
| Schema / migrations | `database/schema.py`, `migrator.py` | [schema & migrations](../orm/schema-migrations.md) |
| Session / engine | `database/db.py`, `session.py` | [query builder](../orm/query-builder.md) |

## Subsystems

| Subsystem | Path | Docs |
|---|---|---|
| Auth | `auth/` | [auth](../subsystems/auth.md) |
| Queues | `queue/` | [queues](../subsystems/queues.md) |
| Events | `events/` | [events](../subsystems/events.md) |
| Broadcasting | `broadcasting/` | [broadcasting](../subsystems/broadcasting.md) |
| Reverb | `reverb/` | [broadcasting](../subsystems/broadcasting.md) |
| Mail | `mail/` | [mail](../subsystems/mail.md) |
| Notifications | `notifications/` | [notifications](../subsystems/notifications.md) |
| Cache | `cache/` | [cache](../subsystems/cache.md) |
| Session | `session/` | [session](../subsystems/session.md) |
| Storage | `storage/` | [storage](../subsystems/storage.md) |
| Scheduling | `scheduling/`, `providers/scheduler_provider.py` | [scheduling](../subsystems/scheduling.md) |
| Encryption | `encryption/`, `facades/crypt.py` | [encryption](../subsystems/encryption.md) |
| Localization | `i18n/` | [localization](../subsystems/localization.md) |
| Observability / logging | `observability/`, `logging/` | [observability](../subsystems/observability.md) |

## Console & packaging

| Area | Path | Docs |
|---|---|---|
| CLI infra + commands | `console/` | [CLI architecture](../console/cli-architecture.md) |
| Project skeleton | `_skeleton/` | — |
| Companion libraries | `packages/arvel-{audit,image,oauth,permission,search}/` | [packages](../packages/overview.md) |
| Reference app | `packages/arvel-ecommerce-demo/` | [demo](../packages/ecommerce-demo.md) |

## Build & quality

| Area | Path | Docs |
|---|---|---|
| Workspace + tool config | root `pyproject.toml` | [quality gates](../contributing/quality-gates.md) |
| Make targets | `Makefile` | [repo & build](../contributing/repo-and-build.md) |
| CI / security | `.github/workflows/`, `.pre-commit-config.yaml` | [quality gates](../contributing/quality-gates.md) |
| Tests + toolkit | `packages/arvel/tests/`, `src/arvel/testing/` | [testing](../contributing/testing.md) |
