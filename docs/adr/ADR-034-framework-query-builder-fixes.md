# ADR-034: Framework Query Builder Critical Fixes

See SAD-043 for full context. This ADR records the two non-obvious decisions.

## ADR-041-01: Route `Model.find()` through the query builder

Status: Accepted

Routing through the QB ensures global scopes (soft-delete, etc.) are applied consistently.
The identity map bypass is an acceptable trade-off for correctness.

## ADR-041-02: Raise `ValueError` on unknown `where_any()` operators

Status: Accepted

Silent equality fallback is a data-correctness bug masquerading as a feature.
Fail loudly, fail early.
