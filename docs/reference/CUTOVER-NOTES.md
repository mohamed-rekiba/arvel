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

The behaviors that originally read as gaps have been triaged and resolved — either fixed in code or confirmed intentional and documented in place:

| Topic | Resolution | Page |
|---|---|---|
| Audit config | Fixed: observers read the provider-bound `AuditConfig` via `audit_config()` (no per-write `.env` reload). `encrypt_values` stays import-time by design — column encryption is schema-lifetime. | [audit](../packages/audit.md) |
| Image alter migration | Stale note: `model_id` is `String(36)` directly in `create_media_table.py`; no separate alter migration exists. | [image](../packages/image.md) |
| Encrypter vs `EncryptedType` | Intentional: two separate paths — versioned column cast (`EncryptedType`) vs app-level `Crypt`. The cast format is deliberately versioned for rotation. | [encryption](../subsystems/encryption.md) |
| Kit + permission | Intentional: the kit does RBAC through the `HasRoles`/`HasPermissions` traits directly (`require_permission` → `has_permission_to`), not the Gate bridge. Test-enforced. | [kit](../kits/ecommerce-kit.md) |

## The old `docs/` tree

Per instruction, the existing `docs/site` (user-facing site) and the SDLC artifacts under `docs/` (architecture SADs, ADRs, PRDs, pipeline) were **not** used as source and were left in place. If any of that content should merge with this set, verify it against the code first — some of it predates current behavior. The decisions in `docs/adr/` are still the authoritative rationale for *why* things are the way they are; this set documents *what* they are now.

## Suggested next steps for cutover

1. Decide the final home (replace `docs/site` internals docs, or stand up a separate "contributing" section).
2. Add a `nav:` block for `docs/` in `mkdocs.yml` (or merge into the existing nav).
3. Resolve the open questions above; turn confirmed bugs into issues and drop the `TODO/QUESTION:` markers once addressed.
4. Run `make docs` (`mkdocs build --strict`) to catch broken links/anchors before publishing.
