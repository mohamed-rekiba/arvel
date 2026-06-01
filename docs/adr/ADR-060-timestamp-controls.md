# ADR-060: Timestamp controls

Status: Accepted (delivered WI-arvel-021)

Eloquent-parity increment (backlog `006`, story S12). Adds opt-out, custom column names,
`touch`/`touch_quietly`, and a `without_timestamps` block. No schema change to existing models.

## ADR-060-01: Hook attachment moves to `Model.__init_subclass__`

Status: Accepted

The `created_at`/`updated_at` auto-fill previously lived in `Timestamps.__init_subclass__`, which
hard-coded the column names. To support custom columns and opt-out, hook attachment moves to
`Model.__init_subclass__`. It attaches the `before_insert`/`before_update` mapper events only when
`__timestamps__` is truthy **and** the model actually has the attribute named by `CREATED_AT` or
`UPDATED_AT`. So a plain model without timestamp columns pays nothing, the `Timestamps` mixin works
as before (it just supplies the default columns), and a model declaring its own timestamp columns
gets auto-fill without the mixin.

## ADR-060-02: `CREATED_AT` / `UPDATED_AT` constants + `__timestamps__` toggle

Status: Accepted

Three `ClassVar`s on `Model`: `__timestamps__: bool = True`, `CREATED_AT: str = "created_at"`,
`UPDATED_AT: str = "updated_at"` (Eloquent's `$timestamps`, `CREATED_AT`, `UPDATED_AT`). The mapper
hooks read the constants — they're declared `str` so `cls.CREATED_AT` type-checks without a
`getattr` widening to `Any`. Setting `__timestamps__ = False` skips hook attachment entirely; the
columns (if present) stay `None` and must be nullable or you'll hit a NOT NULL error — that's the
point of opting out.

SQLAlchemy maps columns to Python attribute names, so "custom column" means a custom attribute
(`inserted_at`) that the developer declares; the constant tells the hooks which attribute to fill.

## ADR-060-03: `without_timestamps()` is a task-local async context

Status: Accepted

`Model.without_timestamps()` returns an async context manager backed by a `ContextVar`
(`_suppress_timestamps`), mirroring `without_events()`. The mapper hooks read the var, so any insert
or update flushed inside the block skips auto-fill. A `ContextVar` (not a plain flag) keeps the
suppression isolated per asyncio task and intact across `await` boundaries — flushes happen during
the awaited `create()`/`save()`, still inside the block. Used for imports and backfills where the
caller supplies explicit timestamps.

## ADR-060-04: `touch(attribute=None)` saves through the event path

Status: Accepted

`touch()` sets `UPDATED_AT` (or a named column) to now and calls `save()`, so it fires
`saving`/`updated`/`saved` and the `before_update` hook still bumps `UPDATED_AT` — Eloquent's
`touch()` parity, including the optional attribute form (`touch("published_at")`).
`touch_quietly()` wraps it in `without_events()`, matching the other `*_quietly` helpers.
