# ADR-022 — Morph Discriminator: Short Class Name

**Date**: 2026-05-17
**Status**: Accepted
**Deciders**: Solution Architect

---

## Context

`MorphOne` / `MorphMany` relations require a discriminator column (`{rel}_type`) that identifies the owning model. Two conventions exist:

1. **Fully-qualified class name (FQCN)**: `"myapp.articles.Article"` — unique across packages but couples the DB to module paths
2. **Short class name**: `"Article"` — matches Laravel's convention; simpler but theoretically ambiguous if two classes share a name

## Decision

Use **short class name** (e.g., `"Article"`) for the `{rel}_type` discriminator column.

## Rationale

- Matches Laravel Eloquent's convention exactly — contributors familiar with Laravel have zero learning curve
- Module paths are refactoring targets; baking an FQCN into a DB column means a rename breaks existing rows
- Arvel apps are modular monoliths (constitution Article III §1) where short name conflicts are extremely rare and linted at boot time
- At `Application` boot, `_loader` validates that no two registered morph-eligible models share the same short class name — raises `ConfigurationError` if they do

## Consequences

- Boot-time validation required: `arvel.console._bootstrap` (and `ApplicationBuilder`) must scan registered models for short-name collisions
- Migration docs must note that renaming a model class requires a data migration to update `{rel}_type` column values
- Tooling (`make:migration`) should warn if it detects a model rename touching a morphable model
