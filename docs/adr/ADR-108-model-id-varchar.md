# ADR-108: Change `media.model_id` from INTEGER to VARCHAR(36)

**Date**: 2026-05-24
**Status**: Accepted

## Context

`Media.model_id` was declared `INTEGER` in WI-026. Laravel's original `polymorphicRelationships`
use a `CHAR(36)` / `BIGINT UNSIGNED` morph pair. Python host models frequently use UUID primary
keys (e.g., the e-commerce demo `Product` uses `uuid4()` PKs). Storing a UUID string in an
INTEGER column silently truncates it on most databases.

## Decision

Change `Media.model_id` to `String(36)` in the SQLAlchemy model and provide an additive
migration (`001_alter_media_model_id.py`) that runs `ALTER TABLE media MODIFY model_id VARCHAR(36)`.

`HasMedia.host_pk()` returns `str(self.id)` so integer PKs store as `"1"`, `"2"`, etc. —
still unique and filterable.

## Consequences

- **Positive**: UUID-PK host models now work correctly.
- **Positive**: No data loss for integer-PK hosts (integers render as string equivalents).
- **Negative**: Slightly wider column (36 bytes vs 8 bytes for BIGINT) — negligible at typical
  media table scales.
- **Negative**: Existing apps that joined on `model_id` as an integer in raw SQL queries must
  cast. ORM users are unaffected.
