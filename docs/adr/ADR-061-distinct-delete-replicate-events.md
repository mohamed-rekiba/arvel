# ADR-061: Distinct soft/hard-delete and replicate events

Status: Accepted (delivered WI-arvel-023)

Eloquent-parity increment (backlog `006`, story S11). Lets listeners tell a soft delete from a hard
delete and react to clones. No schema change.

## ADR-061-01: `trashed` fires on soft delete, alongside `deleted`

Status: Accepted

Soft `delete()` now fires `trashed` then `deleted` (Eloquent order). `deleted` still fires for both
soft and hard deletes — code that just wants "a row went away" keeps working — while `trashed`
fires *only* on the soft path, so a listener can react to the soft-delete specifically. Added to
`_ASYNC_EVENTS` (non-cancellable; the row is already marked by the time it fires).

## ADR-061-02: `force_deleting` / `force_deleted` wrap hard deletes

Status: Accepted

`force_delete()` fires `force_deleting` → `deleting` → (hard DELETE) → `deleted` → `force_deleted`,
matching Laravel's `forceDelete()` which delegates to `delete()` between the force hooks. Both
before-hooks are cancellable (`False` aborts); `force_deleting` is in `_CANCELLABLE_EVENTS`.
`trashed` never fires on this path — that's the signal that distinguishes hard from soft. A model
without `SoftDeletes` has no separate `force_delete` override, so it gets the full set too; harmless,
and consistent.

## ADR-061-03: `replicating` fires on the clone

Status: Accepted

`replicate()` fires `replicating` on the *new* instance (not the source) just before returning it,
matching Eloquent — listeners can scrub or seed fields on the copy. Non-cancellable.

## ADR-061-04: Bulk QueryBuilder deletes stay event-free

Status: Accepted

The story AC mentioned bulk-QB soft deletes firing `trashed`. We deliberately don't: per ADR-065 and
real Eloquent, bulk writes (`query().delete()`, `restore()`, `force_delete()`) are set-based
UPDATE/DELETE statements that never load rows, so there are no instances to fire per-row events on.
Firing fabricated events would be a divergence from Laravel, not parity. Listeners that need per-row
delete events operate on instances. Documented here so the AC gap is intentional, not an oversight.
