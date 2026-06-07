# ADR-028: ModelCollection for Arvent model result sets

Status: Accepted (delivered WI-arvel-037)

Epic 006 Story 8. `QueryBuilder.all()`/`get()` now return a `ModelCollection` — a
`Collection` subclass with the PK- and relation-aware helpers Arvent needs for
model rows (the same helpers Laravel ships on `Eloquent\Collection`).

## Context

`all()` returned the generic `Collection` (a `list` subclass with map/filter/pluck). That's
fine for scalar rows, but model result sets want key-based lookups, batch relation loading, and
re-fetching — the operations Eloquent's model collection provides. Raw/dict result rows
(`select_raw`, `select(cols)`) stay on the plain `Collection`.

## ADR-028-01: subclass, not a new type

Status: Accepted

`ModelCollection(Collection[T])` inherits every existing helper, so nothing that already treats a
result as a list or a `Collection` breaks. Only the model-row return paths in `all()` switch to
`ModelCollection`; dict and raw-SQL rows keep returning `Collection`.

## ADR-028-02: key-aware operations

Status: Accepted

`model_keys()`, `find(key)`, `contains(key|model|predicate)`, `only(*keys)`, `except_(*keys)`,
`diff(other)`, and `intersect(other)` all key off `get_key()` (the model's PK) rather than object
identity — overriding the base `Collection.find`/`only`/`except_`/`contains`/`diff`/`intersect`,
which compare by value or object identity.

## ADR-028-03: batch load / load_missing

Status: Accepted

`load(*relations)` splits requests into async descriptor relations (BelongsToMany / MorphToMany /
MorphOne / MorphMany — routed through the epic-007 `load_async_relation_path`, batched across all
members) and plain SQLAlchemy relations (one `select(model).where(pk IN keys)` with `selectinload`,
results copied onto each member by key). Either way it's a fixed number of queries, never N+1.
`load_missing` only loads relations not yet populated on at least one member.

## ADR-028-04: to_query / fresh

Status: Accepted

`to_query()` returns a `QueryBuilder` scoped to `WHERE pk IN (model_keys)`. `fresh(*relations)`
captures the ordered keys, expires the members (so bulk-update writes that bypassed the identity
map are re-read), re-queries by key with the requested relations eager-loaded, and returns a new
`ModelCollection` in the original order (rows deleted in the meantime drop out).

## ADR-028-05: serialization visibility

Status: Accepted

`make_hidden(*fields)` / `make_visible(*fields)` fan the per-instance visibility helpers out across
every member and return `self` for chaining.
