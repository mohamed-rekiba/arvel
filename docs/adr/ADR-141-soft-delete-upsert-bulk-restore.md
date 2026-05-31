# ADR-141: Soft-delete upsert + bulk restore

Status: Accepted (delivered WI-arvel-022)

Eloquent-parity increment (backlog `006`, story S10). Closes the restore-if-trashed-else-create
gap and adds bulk restore + force-destroy. No schema change.

## ADR-141-01: `restore_or_create` searches with trashed, restores in place

Status: Accepted

`restore_or_create(attributes, values)` runs `with_trashed().where(**attributes).first()`. If a
row exists it restores it when `trashed()`, then returns it — so a soft-deleted row is reused, not
duplicated (the bug the story targets). If none exists it creates with `{**attributes, **values}`,
matching `first_or_create`'s merge. `create_or_restore` is a thin alias; Eloquent ships both names
and people reach for either.

The search deliberately bypasses the soft-delete global scope — otherwise a trashed match would be
invisible and you'd create a duplicate, defeating the point.

## ADR-141-02: Bulk `QueryBuilder.restore()` mirrors bulk `delete()`

Status: Accepted

`restore()` issues a single `UPDATE ... SET deleted_at = NULL` over the current WHERE, the inverse
of the soft-delete branch in `delete()`. It bumps `updated_at` via the same `_touch_updated_at`
helper. Like every bulk write it bypasses per-row model events (Eloquent parity) — callers needing
per-row `restored` hooks restore instances individually.

Because the default soft-delete scope hides trashed rows, `query().restore()` alone matches
nothing. Callers pair it with `only_trashed()` (or `with_trashed().where(...)`), which flips/strips
the scope so the UPDATE targets the trashed rows. Raises `AttributeError` on models without
`SoftDeletes`, consistent with `with_trashed()`/`only_trashed()`.

## ADR-141-03: `trashed()` instance helper

Status: Accepted

`trashed()` returns whether the soft-delete column is set, `False` for models without
`SoftDeletes`. Reused by `restore_or_create` to decide whether a found row needs restoring.

## ADR-141-04: `force_destroy(*ids)` hard-deletes by primary key

Status: Accepted

`force_destroy` accepts varargs or a single iterable (`force_destroy(1, 2)` or
`force_destroy([1, 2])`) and routes through `query().where_in(pk, ids).force_delete()`. Since
`force_delete()` already strips the soft-delete scope, trashed rows are included. Returns the row
count. The primary-key attribute is resolved from the mapper, so composite-PK models would need a
different shape — single-PK is the supported case, the overwhelming default.
