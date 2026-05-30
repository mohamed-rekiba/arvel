## ADR-082 — `arvel-image` runtime layer: synchronous conversions and short-class polymorphism

**Status**: Accepted
**Date**: 2026-05-20
**Supersedes**: —
**Amends**: —
**Depends on**: [ADR-080](ADR-080-arvel-image-pillow-only.md), [ADR-081](ADR-081-arvel-image-medialibrary-scope.md)

## Context

ADR-081 chose to ship laravel-medialibrary v11 parity inside `arvel-image` and shipped only the `media` table as a publishable migration. The runtime layer (the `Media` ORM model, the `HasMedia` trait, and the conversion engine) was deferred. lands that layer. Three architectural calls deserve a record:

1. **Sync vs queued conversions.** Spatie defaults to queued (`->queued()`) and lets you opt into sync (`->nonQueued()`). Arvel doesn't have a Spatie-shaped queue integration in `arvel-image` and bringing one in pulls a transitive dep on `arvel.queue` for a behaviour that 80% of consumers won't see (single-file uploads, one or two conversions, a few hundred ms total).
2. **Polymorphic discriminator value.** The `media` table's `model_type` column can store either the unqualified class name (`"User"`) or the fully-qualified name (`"app.models.User"`). Arvel's existing `MorphOne` / `MorphMany` use the unqualified name (ADR-022). For the trait-driven runtime to share that infra, it needs the same convention.
3. **Default path scheme.** Spatie's default is `{media.id}/{file_name}` for originals and `{media.id}/conversions/{conv}-{file_name}` for conversions. We can mirror it as-is or pick a different default (e.g. with month/year prefixing for filesystem partitioning).

## Decision

### 1. Sync conversions only in v1

`ConversionRunner.run` executes synchronously inside `FileAdder.to_media_collection`, before that coroutine returns. Pillow's CPU work is wrapped in `anyio.to_thread.run_sync` to avoid blocking the event loop. There is no `.queued()` / `.non_queued()` toggle.

### 2. Short class name as polymorphic discriminator

`Media.model_type` stores `type(host).__name__` — the unqualified class name. Same convention as `MorphOne` / `MorphMany` per ADR-022. The trait can therefore reuse `MorphMany(Media, name="model")` directly.

### 3. Default path scheme matches Spatie verbatim

`DefaultPathGenerator`:
- Original: `{media.id}/{file_name}`
- Conversion: `{media.id}/conversions/{name}-{file_name}`

## Consequences

✅ **Sync conversions** keep the package stand-alone — apps that don't use `arvel.queue` still get the full media-library API. Apps that need async dispatch can wrap the call in their own job. Documented in DXD-026 and the package README.
✅ **Short-class polymorphism** lets the trait reuse the existing `MorphMany` accessor (zero code duplication) and stays consistent with the rest of the framework.
✅ **Default path scheme** matches Spatie verbatim — Laravel migrators don't have to rewrite their URL handlers.

⚠️ **Sync conversions** mean a slow Pillow operation can extend a request handler's latency. Mitigated by `anyio.to_thread.run_sync` (one event-loop thread); explicit in PRD risk table; future async dispatch is a separate WI when a real consumer asks.
⚠️ **Short-class polymorphism** has the same theoretical collision risk as the rest of the framework: if two unrelated mapped classes share `__name__` (e.g. `app.models.User` and `app.legacy.User`), media rows could be cross-pollinated. Documented in the trait docstring and in ADR-022; not new debt.

## Alternatives considered

- **(A) Queued conversions via arvel.queue.** Rejected: pulls `arvel.queue` (and the consumer's queue config) into `arvel-image`'s critical path. Sync mode is simpler, deterministic, and matches the framework's "deterministic by default, opt-in async" rule from the constitution.
- **(B) FQN polymorphic discriminator.** Rejected: would require parallel infrastructure to ADR-022 just for this one feature. Not worth diverging.
- **(C) Date-prefixed path scheme** (`{yyyy}/{mm}/{id}/{file_name}`). Rejected for the default — Spatie's `{id}/...` is what migrators expect. Consumers who want partitioning bind their own `PathGenerator`.
- **(D) Async dispatch in v1 with a `.queued()` opt-in.** Rejected per `001-no-overengineering.mdc` — there is no concrete consumer asking for it; can be added without breaking the sync default.
