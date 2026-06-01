## ADR-134 — `arvel-image` runtime layer: synchronous conversions and short-class polymorphism

**Status**: Accepted
**Date**: 2026-05-20
**Supersedes**: —
**Amends**: —
**Depends on**: [ADR-132](ADR-132-arvel-image-pillow-only.md), [ADR-133](ADR-133-arvel-image-medialibrary-scope.md)

## Context

ADR-133 chose to ship laravel-medialibrary v11 parity inside `arvel-image` and shipped only the `media` table as a publishable migration. The runtime layer (the `Media` ORM model, the `HasMedia` trait, and the conversion engine) was deferred. lands that layer. Three architectural calls deserve a record:

1. **Sync vs queued conversions.** Spatie defaults to queued (`->queued()`) and lets you opt into sync (`->nonQueued()`). Arvel doesn't have a Spatie-shaped queue integration in `arvel-image` and bringing one in pulls a transitive dep on `arvel.queue` for a behaviour that 80% of consumers won't see (single-file uploads, one or two conversions, a few hundred ms total).
2. **Polymorphic discriminator value.** The `media` table's `model_type` column can store either the unqualified class name (`"User"`) or the fully-qualified name (`"app.models.User"`). Arvel's existing `MorphOne` / `MorphMany` use the unqualified name (ADR-066). For the trait-driven runtime to share that infra, it needs the same convention.
3. **Default path scheme.** Spatie's default is `{media.id}/{file_name}` for originals and `{media.id}/conversions/{conv}-{file_name}` for conversions. We can mirror it as-is or pick a different default (e.g. with month/year prefixing for filesystem partitioning).

## Decision

### 1. Sync conversions only in v1

`ConversionRunner.run` executes synchronously inside `FileAdder.to_media_collection`, before that coroutine returns. Pillow's CPU work is wrapped in `anyio.to_thread.run_sync` to avoid blocking the event loop. There is no `.queued()` / `.non_queued()` toggle.

### 2. Short class name as polymorphic discriminator

`Media.model_type` stores `type(host).__name__` — the unqualified class name. Same convention as `MorphOne` / `MorphMany` per ADR-066. The trait can therefore reuse `MorphMany(Media, name="model")` directly.

### 3. Default path scheme matches Spatie verbatim

`DefaultPathGenerator`:
- Original: `{media.id}/{file_name}`
- Conversion: `{media.id}/conversions/{name}-{file_name}`

## Consequences

✅ **Sync conversions** keep the package stand-alone — apps that don't use `arvel.queue` still get the full media-library API. Apps that need async dispatch can wrap the call in their own job. Documented in DXD-026 and the package README.
✅ **Short-class polymorphism** lets the trait reuse the existing `MorphMany` accessor (zero code duplication) and stays consistent with the rest of the framework.
✅ **Default path scheme** matches Spatie verbatim — Laravel migrators don't have to rewrite their URL handlers.

⚠️ **Sync conversions** mean a slow Pillow operation can extend a request handler's latency. Mitigated by `anyio.to_thread.run_sync` (one event-loop thread); explicit in PRD risk table; future async dispatch is a separate WI when a real consumer asks.
⚠️ **Short-class polymorphism** has the same theoretical collision risk as the rest of the framework: if two unrelated mapped classes share `__name__` (e.g. `app.models.User` and `app.legacy.User`), media rows could be cross-pollinated. Documented in the trait docstring and in ADR-066; not new debt.

## Alternatives considered

- **(A) Queued conversions via arvel.queue.** Rejected: pulls `arvel.queue` (and the consumer's queue config) into `arvel-image`'s critical path. Sync mode is simpler, deterministic, and matches the framework's "deterministic by default, opt-in async" rule from the constitution.
- **(B) FQN polymorphic discriminator.** Rejected: would require parallel infrastructure to ADR-066 just for this one feature. Not worth diverging.
- **(C) Date-prefixed path scheme** (`{yyyy}/{mm}/{id}/{file_name}`). Rejected for the default — Spatie's `{id}/...` is what migrators expect. Consumers who want partitioning bind their own `PathGenerator`.
- **(D) Async dispatch in v1 with a `.queued()` opt-in.** Rejected per `001-no-overengineering.mdc` — there is no concrete consumer asking for it; can be added without breaking the sync default.

---

## Merged: `HasMedia` aliases and `HasMediaMixin` re-export (was ADR-134)

**Status**: Accepted
**Date**: 2026-05-24

## Context

`HasMedia` shipped with `add_media()` and `clear_media_collection()`. The e-commerce demo
expected `attach_media()` (one-call attach with collection name) and `delete_media()`. The name
mismatch led the demo to define its own `HasMediaMixin` instead of using the framework class.

## Decision

1. Add `attach_media(source, *, file_name, collection)` as a one-call alias that chains
   `add_media().to_media_collection(collection)`.
2. Add `delete_media(collection)` as an alias for `clear_media_collection(collection)`.
3. Export `HasMediaMixin = HasMedia` from `arvel_image/__init__.py`.

`add_media()` and `clear_media_collection()` are kept unchanged (existing callers unaffected).

## Consequences

- Positive: Demo's `HasMediaMixin` can be deleted; one canonical class in the framework.
- Positive: `attach_media()` is more ergonomic — single call vs. `add_media().to_media_collection()` chain.
- Negative: None. All three are additive.

---

## Merged: Change `media.model_id` from INTEGER to VARCHAR(36) (was ADR-134)

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
