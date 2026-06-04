# Schema Plan — WI-arvel-001

**Status**: No schema changes in this WI.

> **Adapted artifact.** The schema's `planning-dba` stage canonically produces files under `db/schema/`, `db/migrations/`, `db/seeds/`. This polish epic changes no SQL — a 1-line note is the honest output.

## What stays the same

The `media` table created by `packages/arvel-image/src/arvel_image/migrations/create_media_table.py` is unchanged. Column set, indexes, constraints, polymorphic morph columns (`model_type`, `model_id`) all stay as-is.

## Why no migration is needed

| Story | Touches schema? | Notes |
|---|---|---|
| 2 — Public surface | No | Renames are Python-only |
| 3 — Error quality | No | Exception text only |
| 4 — Type narrowness | No | TypedDicts on Python side, no SQL types affected |
| 5 — MRO guard | No | `__init_subclass__` on mixin |
| 6 — Dead code | No | Helper deletions, no row shape change |
| 7 — SSRF guard | No | URL-fetcher hardening, no persistence change |
| 8-11 — Tests | No | Tests use existing tables |
| 12, 13 — Docs | No | Markdown only |
| 14 — Verify | No | Verification only |

## Confirmation

The `media` table schema reference will continue to be `packages/arvel-image/src/arvel_image/migrations/create_media_table.py`. The polish pass does not touch this file.
