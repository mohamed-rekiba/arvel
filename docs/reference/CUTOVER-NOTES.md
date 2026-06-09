# Cutover notes

Notes for whoever migrates this documentation into its final home. These are the assumptions, open questions, and gaps surfaced while writing `docs/` from source.

## What this is

`docs/` is a **contributor / framework-internals** documentation set, written from scratch against the code in `packages/`. It explains how Arvel works under the hood and how to extend it — it is not the application-developer site under `docs/site`, which was left untouched per instruction.

It covers: architecture (container, providers, bootstrap, config, facades), HTTP, the Arvent ORM, 13 subsystems, the CLI, the 5 companion packages + kit, and the contributing workflow.

## Assumptions made

- **MkDocs Material + Mermaid** is the render target. `mkdocs.yml` already enables Mermaid via the Material superfences, so diagrams render as-is. If this set is wired into a nav, it needs its own `nav:` entries (not yet added).
- **Relative links** between pages assume the current `docs/` tree layout. Moving the tree means re-rooting links.
- Source is the **current code on the working branch**, not any release tag.

## Open questions for SMEs

These are behaviors that read as gaps or inconsistencies in the source. Each is flagged inline on its page as `TODO/QUESTION:`. They need a maintainer's call — bug, intentional, or doc-only:

| Topic | Question | Page |
|---|---|---|
| Cache `database` store | Hardcoded to in-memory SQLite — should it use the app DB / a `CACHE_DATABASE_URL`? | [cache](../subsystems/cache.md) |
| Session cookie flags | `StartSession` hardcodes `HttpOnly`/`SameSite=Lax`; `SESSION_SECURE`/`SESSION_SAME_SITE`/`SESSION_ENCRYPT` are unused. Intended? | [session](../subsystems/session.md) |
| Storage `app_key` | Provider doesn't pass `app_key`, so local `temporary_url()` raises. Wire `APP_KEY` in? | [storage](../subsystems/storage.md) |
| Azure temporary URLs | `AzureDriver.temporary_url` raises `NotImplementedError`. | [storage](../subsystems/storage.md) |
| Scheduler fields | `inMaintenanceMode()` / `outputTo()` stored but never read by the kernel. | [scheduling](../subsystems/scheduling.md) |
| Audit config | Container-bound `AuditConfig` is unused at runtime; `encrypt_values` fixed at import. | [audit](../packages/audit.md) |
| Image alter migration | `001_alter_media_model_id.py` not in `publishes()` — upgrade path easy to miss. | [image](../packages/image.md) |
| CLI async loops | `cache:*` and `schedule:run` run a nested `asyncio.run()` inside the outer loop. | [CLI architecture](../console/cli-architecture.md) |
| `Application.run(args)` | Ignores `args` — scheduled/programmatic invocation can't pass flags. | [CLI architecture](../console/cli-architecture.md) |
| Stub commands | `key:rotate`, parts of `optimize` (`route:cache`, `event:cache`) are honest stubs. | [CLI architecture](../console/cli-architecture.md) |
| Encrypter vs `EncryptedType` | Two wire formats (v2 app-level vs v1 column cast). Confirm both are intended. | [encryption](../subsystems/encryption.md) |
| Kit + permission | The kit uses permission models without `PermissionServiceProvider`, so the Gate bridge doesn't run. | [kit](../kits/ecommerce-kit.md) |
| Broadcasting bridge | No built-in bridge from `redis-pubsub` publishing to the Reverb WebSocket server. | [broadcasting](../subsystems/broadcasting.md) |

## The old `docs/` tree

Per instruction, the existing `docs/site` (user-facing site) and the SDLC artifacts under `docs/` (architecture SADs, ADRs, PRDs, pipeline) were **not** used as source and were left in place. If any of that content should merge with this set, verify it against the code first — some of it predates current behavior. The decisions in `docs/adr/` are still the authoritative rationale for *why* things are the way they are; this set documents *what* they are now.

## Suggested next steps for cutover

1. Decide the final home (replace `docs/site` internals docs, or stand up a separate "contributing" section).
2. Add a `nav:` block for `docs/` in `mkdocs.yml` (or merge into the existing nav).
3. Resolve the open questions above; turn confirmed bugs into issues and drop the `TODO/QUESTION:` markers once addressed.
4. Run `make docs` (`mkdocs build --strict`) to catch broken links/anchors before publishing.
