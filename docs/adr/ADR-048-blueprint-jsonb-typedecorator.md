# ADR-048: `Blueprint.jsonb()` via TypeDecorator

**Status**: Accepted
**Date**: 2026-05-24

## Context

The Schema DSL's `Blueprint.json()` emits `JSON`, but PostgreSQL `JSONB` is required for GIN
indexes and containment queries. Migrations needing JSONB had to import from
`sqlalchemy.dialects.postgresql` directly, coupling migration files to a specific dialect.

## Decision

Add a `_JsonB` TypeDecorator that emits `JSONB` on PostgreSQL and degrades to `JSON` on all
other dialects. Expose it as `Blueprint.jsonb(name)`. Follow the identical pattern used by
`_TsVector` in the same file.

## Consequences

- Positive: Migration files stay dialect-neutral. GIN indexing of JSONB columns is idiomatic.
- Positive: `_TsVector` pattern is proven in production — `_JsonB` reuses without invention.
- Negative: None. `Blueprint.json()` is unchanged; `jsonb()` is purely additive.
