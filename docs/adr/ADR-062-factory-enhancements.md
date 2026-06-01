# ADR-062: Factory enhancements

Status: Accepted (delivered WI-arvel-023... WI-arvel-024)

Eloquent-parity increment (backlog `006`, story S13). Brings `Factory` closer to Laravel's
`HasFactory` surface: M2M attachment, soft-deleted state, Faker in callbacks, quiet creation, and
per-connection persistence. No schema change.

## ADR-062-01: `has_attached(relation, factory, *, count, pivot)`

Status: Accepted

After the parent is flushed, the related factory builds `count` rows and each is linked through the
`BelongsToMany` accessor's `attach(pk, **pivot)`. `pivot` columns are written on every pivot row.
Children are created via `create()` so their own `has`/`has_attached`/callbacks run too. We don't
`session.expire` the relation afterwards (unlike `has()` for true `relationship()`s) — the
`BelongsToMany` accessor isn't a mapped attribute, and `attach()` already invalidates its eager
cache.

## ADR-062-02: `trashed()` state

Status: Accepted

Sets the soft-delete column (`__arvel_soft_delete_column__`, default `deleted_at`) to now on each
made instance, after construction — the column is `init=False`, so it can't go through `__init__`.
Raises `AttributeError` if the model lacks `SoftDeletes`, matching the rest of the soft-delete API.
The row persists already-trashed (hidden by the default scope, visible via `with_trashed()`).

## ADR-062-03: Faker passed to callbacks

Status: Accepted

`after_making` / `after_creating` callbacks now receive a shared `faker.Faker` instance as the
second argument instead of `None`. Faker is a dev-only dependency, so `_faker()` imports it lazily
and caches the instance (in a one-slot list to dodge the constant-redefinition lint); if it's not
installed, callbacks get `None` as before. The callback contract `(_, faker)` is unchanged.

## ADR-062-04: `create_quietly()`

Status: Accepted

Wraps `create()` in `without_events()` so any model lifecycle events triggered during the build
(children, attached rows, observers on the created models) are muted — Laravel's `createQuietly`.

## ADR-062-05: `connection(name)` per-factory routing

Status: Accepted

Records a named connection; `create()` opens a session from `DB.session_maker_for(name)`, binds it
as the active session for the whole build (so children and pivot attaches use it too), commits, and
restores the previous session. Added `DB.session_maker_for()` (public maker lookup, reused by
`DB.connection()`) and `DB.forget_named()` (drop a registration, used by tests). Without a name, the
ambient session is used — unchanged default.
