# Architecture

Internal engineering docs for how Arvel is built. These are not part of the public site (`docs/site/`) — they're the reference the squad reads when working on the framework itself.

Two kinds of document live here.

## Naming convention

Every file is `TYPE-NNN-slug.md`. Two type codes:

| Type | Meaning | Numbering |
|---|---|---|
| `ARCH-NNN` | Topic guide — a living, evergreen reference for how a part of the framework works today | Sequential; the number also encodes the recommended reading order |
| `SAD-NNN` | Solution Architecture Document — a point-in-time record of the decisions for one work item | Sequential per the project's `SAD` series; see `015-context-engineering.mdc` |

The H1 of each file repeats its ID (`# ARCH-002 — Bootstrap & lifecycle`). Slugs are lowercase kebab-case. New guides take the next free `ARCH-NNN`; new SADs the next free `SAD-NNN`.

## Topic guides — living internals reference

Read these to understand how the framework works today. Start with `ARCH-001`, then `ARCH-002` — the register/boot split governs everything else.

| Guide | What it covers |
|---|---|
| [ARCH-001 — Overview](ARCH-001-overview.md) | The whole framework in two ideas: a container and a provider pipeline. Start here. |
| [ARCH-002 — Bootstrap & lifecycle](ARCH-002-bootstrap-lifecycle.md) | `configure()` → `create()` → `boot()` → serving → `shutdown()`; provider ordering; `into_asgi()` and the middleware stack. |
| [ARCH-003 — Service container](ARCH-003-service-container.md) | DI core: lifetimes, resolution order, autowiring, scopes, async bindings, contextual bindings. |
| [ARCH-004 — Service providers](ARCH-004-service-providers.md) | The unit of bootstrap: the `register`/`boot`/`shutdown` contract and provider helpers. |
| [ARCH-005 — Facades](ARCH-005-facades.md) | Process-wide static accessors, how each binds, and the unbound-error map. |
| [ARCH-006 — Configuration](ARCH-006-configuration.md) | The two config systems, the config-file → env cascade, and typed `ArvelSettings`. |

## Solution Architecture Documents (SADs)

Point-in-time records of architecture decisions for a work item. Each has been verified against current source; where the code and the original decision diverged, the doc reflects what shipped (notably SAD-004's SSRF posture).

| SAD | Subject |
|---|---|
| [SAD-001](SAD-001-local-storage-serving.md) | Framework-level local file serving (signed URLs, serve route). |
| [SAD-002](SAD-002-config-file-cascade.md) | Config-file cascade for all typed settings via a pydantic-settings source. |
| [SAD-003](SAD-003-storage-link-static-serving.md) | Static serving for `storage:link` (`/storage` mount). |
| [SAD-004](SAD-004-arvel-image.md) | `arvel-image` polish/hardening, including the URL-fetcher SSRF guard. |
| [SAD-005](SAD-005-console-runtime-architecture.md) | Console / CLI runtime: entrypoint flow, needs-based bootstrap, command discovery. |
| [SAD-006](SAD-006-arvon.md) | Arvon — the fluent, immutable datetime value type. |
