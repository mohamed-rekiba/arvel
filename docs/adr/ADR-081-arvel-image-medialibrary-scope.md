## ADR-081 — `arvel-image` scope: also ship laravel-medialibrary parity

**Status**: Accepted
**Date**: 2026-05-21
**Supersedes**: —
**Amends**: [ADR-080](ADR-080-arvel-image-pillow-only.md)

## Context

When ADR-080 landed, `arvel-image` was framed as a stateless Pillow wrapper — a port of [`spatie/image`](https://spatie.be/docs/image/v3) only. That covers "transform these bytes". It does **not** cover the much more common Laravel use case: *"attach this file to my model, generate thumbnails, give me a URL back."* That second workflow is [`spatie/laravel-medialibrary`](https://spatie.be/docs/laravel-medialibrary/v11) — a separate Spatie package, but most Laravel apps that pull in Spatie image work also pull in medialibrary.

Splitting Arvel's port across two packages (`arvel-image` for transforms, a hypothetical `arvel-medialibrary` for the model association) would give us:

- Two PyPI extras (`arvel[image]`, `arvel[medialibrary]`) with overlapping dependencies.
- Two README mapping tables a Laravel migrator has to read.
- Two `vendor:publish` tags consumers have to remember.

For a parity story aimed at Laravel migrators, a single "image stuff lives here" package is closer to what they expect.

## Decision

`arvel-image` ships **both** Spatie surfaces:

1. The fluent transform API (`arvel_image.Image`, ADR-080 — unchanged).
2. A laravel-medialibrary v11-compatible `media` table plus `ImageServiceProvider` that registers it as publishable under tag `arvel-image`.

The `media` table mirrors Spatie's v11 schema verbatim — id, polymorphic `model_type` / `model_id`, `uuid`, `collection_name`, `name`, `file_name`, `mime_type`, `disk`, `conversions_disk`, unsigned `size`, JSON columns for `manipulations` / `custom_properties` / `generated_conversions` / `responsive_images`, indexed nullable `order_column`, nullable timestamps. Full `Media` ORM model and `HasMedia` trait are out of scope for this WI — the migration is the foundation; the model + trait land when first asked for.

Apps that only want the transform API still get a clean install: `from arvel_image import Image` works without booting a provider. The migration only lands in `database/migrations/` if the app explicitly runs `arvel vendor:publish --tag=arvel-image`.

## Consequences

✅ One package, one extras flag, one README. Laravel migrators don't have to learn two arvel-* names for what they think of as "the image package".
✅ ADR-080's Pillow-only constraint is unchanged — the transform code paths still don't shell out, still have full PEP-561 typing, still have the same dependency footprint at install time.
✅ The migration is opt-in (publish, then migrate). Apps that don't need the `media` table pay zero cost.

⚠️ `arvel-image` now depends on `arvel` (it imports `ServiceProvider`). Pre-ADR-081 the package was technically usable without arvel installed. In practice it shipped only via `arvel[image]`, so this is paperwork rather than a real regression. Documented in the README.
⚠️ The decision means a future "I want the model association but not the transforms" user can't take just half. Acceptable: the transform code is small (~180 lines, Pillow-only), and Pillow is already in most Python images.
⚠️ The `Media` ORM model and `HasMedia` trait remain TODO. Until they ship, `vendor:publish` produces a usable schema but Arvel-side ergonomics around it are application-owned. Tracked as a post-WI-025 follow-up.

## Alternatives considered

- **(A) Keep `arvel-image` stateless; ship a separate `arvel-medialibrary`.** Rejected: doubles the surface area Laravel migrators have to discover, and the two are coupled in practice (every laravel-medialibrary install also wants `spatie/image` for the conversions).
- **(B) Bake the `Media` model + `HasMedia` trait into this WI.** Rejected per `001-no-overengineering`: the user asked for the migration; the model/trait have multiple valid shapes (sync vs async API, eager vs lazy conversions, disk abstraction options) that deserve a dedicated design pass.
