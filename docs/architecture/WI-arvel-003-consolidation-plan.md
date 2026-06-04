# WI-arvel-003 — Adapted SAD: Consolidation Plan

**Work Item**: WI-arvel-003
**Type**: Hygiene / documentation reorganization
**Date**: 2026-06-05
**Status**: Approved (autonomous mode)

> **Adapted artifact.** The schema's `planning-sa` stage canonically produces a full SAD (system design, technology choices, threat model, OpenAPI). This WI ships zero source-code architecture and zero API surface. What this document covers: the **shape** of the consolidation operation that Stage 3b will execute. The materialized merged `SAD-004 — arvel-image` is the *outcome*, not this document.

## What does not change

| Concern | Status | Why |
|---|---|---|
| arvel-image package layout | Unchanged | Doc-only consolidation; no Python file moved or renamed |
| arvel-image public API | Unchanged | No `__all__` edits, no demotions, no additions |
| arvel-image SQL schema | Unchanged | No migration; `media` table identical |
| Ecommerce kit code | Unchanged | Only compose/env files touched |
| ADRs 1–131 | Unchanged | Compact-image-only renumber scope (user-approved) |
| Pipeline audit history | Unchanged | `docs/pipeline/**` is append-only audit truth |
| `arvel.storage` driver protocol | Unchanged | No new drivers; minio reaches the kit through the existing `s3` driver |

## What does change

### 1. ADR topology

```
BEFORE:                                  AFTER:
docs/adr/                                docs/adr/
├── ADR-132-arvel-image-pillow-only.md  ├── ADR-132-arvel-image.md           (MERGED, 7→1)
├── ADR-133-arvel-image-medialibrary-   ├── ADR-133-config-file-settings-    (RENAMED from 136)
│   scope.md                            │   source.md
├── ADR-134-arvel-image-medialibrary-   ├── ADR-134-public-storage-static-   (RENAMED from 137)
│   runtime.md                          │   mount.md
├── ADR-135-ssrf-guard-ipaddress.md     │
├── ADR-136-config-file-settings-       │
│   source.md                           │
├── ADR-137-public-storage-static-      │
│   mount.md                            │
├── ADR-138-arvel-image-polish-         │
│   design-decisions.md                 │
├── ADR-139-minio-fixture-copy-vs-      │
│   extract.md                          │
└── ADR-140-aiohttp-cve-pin-scope.md    │
                                         (next free: ADR-135)
```

Net: 9 files → 3 files. Six deletions, two renames, one substantial rewrite.

### 2. SAD topology

```
BEFORE:                                  AFTER:
docs/architecture/                       docs/architecture/
├── SAD-004-arvel-image-polish.md       ├── SAD-004-arvel-image.md  (MERGED, 2→1)
└── SAD-005-arvel-image-post-1.0-       └──
    followups.md
                                         (next free: SAD-006)
```

### 3. Ecommerce kit compose

Three new services added to `kits/arvel-ecommerce-kit/docker-compose.yml`:

| Service | Image (pinned) | Purpose |
|---|---|---|
| `minio` | `minio/minio:<current-stable>` | S3-compatible object store |
| `createbuckets` | `minio/mc:<current-stable>` | One-shot bucket bootstrap (matches `STORAGE_S3_BUCKET`) |
| `caddy` | `caddy:<current-stable>` | Reverse-proxy `/storage/*` from frontend origin to minio |

Backend depends on `minio:service_healthy`. Caddy depends on `minio:service_healthy`. createbuckets runs once and exits.

### 4. Env-var reconciliation

`config/filesystems.py` already reads `STORAGE_S3_KEY` and `STORAGE_S3_SECRET`. README and `.env.example` will adopt those names.

## Consolidation principles (applied uniformly across Story 3 and Story 4)

1. **Lowest-number-wins**: The merged ADR keeps `ADR-132`; the merged SAD keeps `SAD-004`. This minimizes the cross-reference rewrite blast radius.
2. **Subsumes block**: Both the merged ADR and SAD carry a `## Subsumes` section listing every absorbed file. Future readers can audit what was folded where; pipeline handoffs and stage-log retain their original ADR/SAD references unchanged.
3. **Verbatim preservation of decision text**: Each absorbed ADR's "Decision" section is preserved verbatim as a `§ N` heading in the merged ADR. The "Context" sections are deduplicated (the shared "WI-arvel-001 polish pass" context only appears once).
4. **Renumbering scope**: Compact image-only (user choice 3). The merged ADR-132 keeps its number; the only renumbering is the framework-storage pair (136 → 133, 137 → 134) closing the gap.

## OpenAPI

**Not produced.** WI-arvel-003 introduces zero new HTTP routes and modifies zero existing route signatures. `arvel-image` is a library; the kit's HTTP surface is unchanged. The schema's `docs/api/openapi.yaml` hard-gate criterion is genuinely N/A for this WI.

## Threat model delta

No new attack surface introduced. The new MinIO service is reachable only inside the compose network (no host port mapping for `minio:9000` is strictly required — exposed for developer console access at `:9001`). Default credentials labeled dev-only. The `SSRF guard` decision from absorbed ADR-135 is preserved verbatim in `ADR-132 § 4`.

## Why this is not its own ADR

Two reasons:

1. **No architectural decision is being made** — the SHAPE of the consolidation was decided in the user AskQuestion (single ADR / fold-in / compact / compose). This document records that shape; it does not propose alternatives.
2. **Adding an ADR-NNN-docs-consolidation would itself need to be merged later.** The hygiene operation should not pollute its own target.

The consolidation rationale is captured in this work-item-scoped file alongside `WI-arvel-001-no-schema-change.md` and `WI-arvel-002-no-schema-change.md`, matching the established pattern.
