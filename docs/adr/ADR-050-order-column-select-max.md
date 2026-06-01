# ADR-050: order_column assigned via SELECT MAX + 1

**Date**: 2026-05-24
**Status**: Accepted

## Context

`order_column` on the `media` table controls retrieval order within a collection.
requires it to be auto-assigned on insert. We need a strategy that works
without adding a DB sequence or trigger.

## Decision

Assign `order_column = SELECT MAX(order_column) + 1` scoped to `(model_type, model_id,
collection_name)` within the same ORM session, immediately before `Media.create()`.

## Consequences

- Simple; no migration needed (column already exists).
- Not safe for concurrent inserts from multiple workers. Under the framework's typical
  single-async-task-per-request model this is acceptable.
- If two concurrent inserts race, both may get the same `order_column`. Acceptable —
  `id` ASC is the tiebreaker and the order is still deterministic.
- Documented limitation; not a defect.
