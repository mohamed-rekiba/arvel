# ADR-095: PostgreSQL FTS — Thin Helpers Over Searchable Mixin

**Status**: Accepted
**Date**: 2026-05-23

## Decision

Add four thin helpers to `Blueprint` and `QueryBuilder` for PostgreSQL full-text search:
`tsvector()`, `gin_index()`, `where_full_text()`, `order_by_relevance()`.

## Context

Arvel's query builder and schema DSL had no FTS support. Developers needed to use `where_raw()` and `raw_column()`, which are verbose, non-discoverable, and provide no guardrails (e.g., no validation of `tsquery_fn`).

Two alternatives were considered:

- **Option A** (chosen): Four thin helpers, three files changed, no new abstractions.
- **Option B**: A `Searchable` mixin that auto-declares the column and exposes `Model.search()`.

## Rationale

Option B was rejected because vector population strategy (DB trigger, application-level update, or `to_tsvector()` computed column) varies per application and cannot be generalized at the framework level without opinionated choices that some apps won't want. Forcing a migration generation hook and a vector maintenance story into the framework before any real consumer exists violates YAGNI.

Option A delivers the full ergonomic improvement (typed, discoverable, safe bind params, allowlisted `tsquery_fn`) without coupling the framework to a particular population strategy.

## Consequences

- Consuming apps must maintain their own vector population logic (documented, not hidden).
- A `Searchable` mixin can be added later as a higher-level optional abstraction built on these primitives.
- `ts_rank_cd` and custom normalization weights remain accessible via `order_by_raw()`.
