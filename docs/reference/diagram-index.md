# Diagram index

Every diagram in this documentation, by page. All are Mermaid; they render in MkDocs Material.

## Architecture

| Diagram | Page |
|---|---|
| 10,000-foot view (app → arvel → stack) | [README](../README.md) |
| Layered design | [overview](../architecture/ARCH-001-overview.md) |
| Bootstrap sequence (register → boot → shutdown) | [bootstrap & lifecycle](../architecture/ARCH-002-bootstrap-lifecycle.md) |
| Container resolution order | [service container](../architecture/ARCH-003-service-container.md) |
| Provider lifecycle states | [service providers](../architecture/ARCH-004-service-providers.md) |
| Two config systems | [configuration](../architecture/ARCH-006-configuration.md) |
| Facade binding | [facades](../architecture/ARCH-005-facades.md) |

## HTTP

| Diagram | Page |
|---|---|
| `register_with_app` mounting pipeline | [routing](../http/routing.md) |
| Request flow (ASGI vs route middleware) | [middleware](../http/middleware.md) |
| Two validation layers | [requests & validation](../http/requests-validation.md) |
| `JsonResource` post-processing | [resources](../http/resources.md) |
| Exception handler flow | [exceptions](../http/exceptions.md) |

## ORM

| Diagram | Page |
|---|---|
| What `Model` is composed of | [model internals](../orm/model-internals.md) |
| Active-session acquisition | [query builder](../orm/query-builder.md) |
| Relation discovery | [relationships](../orm/relationships.md) |
| Two casting layers | [casts](../orm/casts.md) |
| Migration pipeline | [schema & migrations](../orm/schema-migrations.md) |

## Subsystems

| Diagram | Page |
|---|---|
| Auth: three surfaces | [auth](../subsystems/auth.md) |
| Job lifecycle (state machine) | [queues](../subsystems/queues.md) |
| Inline vs queued events | [events](../subsystems/events.md) |
| Publishing side vs realtime side | [broadcasting](../subsystems/broadcasting.md) |
| Mail shape | [mail](../subsystems/mail.md) |
| Notification dispatch | [notifications](../subsystems/notifications.md) |
| Manager + stores | [cache](../subsystems/cache.md) |
| Scheduler run flow | [scheduling](../subsystems/scheduling.md) |
| Encrypter key derivation | [encryption](../subsystems/encryption.md) |
| Locale resolution | [localization](../subsystems/localization.md) |
| Observability wiring | [observability](../subsystems/observability.md) |

## Console & packages

| Diagram | Page |
|---|---|
| CLI invocation flow | [CLI architecture](../console/cli-architecture.md) |
| Five libraries | [packages overview](../packages/overview.md) |
| Audit: automatic vs manual | [audit](../packages/audit.md) |
| Image: two layers | [image](../packages/image.md) |
| OAuth login sequence | [oauth](../packages/oauth.md) |
| Permission shape | [permission](../packages/permission.md) |
| Search shape | [search](../packages/search.md) |

## Contributing

| Diagram | Page |
|---|---|
| Quality gate pipeline | [quality gates](../contributing/quality-gates.md) |
| Fakes vs Testcontainers | [testing](../contributing/testing.md) |
| Subsystem shape | [extending](../contributing/extending.md) |
