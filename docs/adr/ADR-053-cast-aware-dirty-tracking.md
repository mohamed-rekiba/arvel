# ADR-053: Cast-aware Dirty Tracking

Status: Accepted

Eloquent-parity increment (backlog `006`, Sprint B: story S4). No HTTP or schema
surface — recorded as an ADR.

## ADR-053-01: Compare original vs current at the *cast* level

Status: Accepted

`is_dirty` / `get_dirty` previously trusted SQLAlchemy's raw attribute history. That's
right for plain columns but produces false positives for custom casts: a JSON cast can
re-serialize `{"a": 1, "b": 2}` to a different string than the stored one (key order,
spacing), so the raw strings differ even though the value didn't. (Built-in scalar casts
like boolean-over-int rarely trip this, because SQLAlchemy keeps the post-cast value in
`committed_state` and `1 == True` in Python.)

`original_is_equivalent(key)` mirrors Eloquent's method: if the raw values differ, fall
back to comparing the **read-cast** values. Equal cast values ⇒ not dirty. `is_dirty` and
`get_dirty` filter SQLAlchemy-changed keys through it, so `"1"` vs `1`, decimal strings,
and re-serialized JSON read clean while genuine changes still read dirty.

## ADR-053-02: `get_original` casts, `get_raw_original` doesn't

Status: Accepted

Split the original-value accessors to match Laravel:

- `get_raw_original(key=None)` returns the pre-cast committed value (what the old
  `get_original` returned).
- `get_original(key=None)` applies the read cast, so it returns the same shape callers see
  from a live attribute read.

## ADR-053-03: Guard the `NO_VALUE` sentinel

Status: Accepted

A pending (added, not-yet-flushed) instance carries SQLAlchemy's `NO_VALUE` sentinel in
`committed_state` for attributes with no committed original — which is exactly the state
`create()` snapshots through `get_dirty`. Both `original_is_equivalent` and `_read_cast`
treat `NO_VALUE` as "no original" (genuinely dirty / passthrough) rather than feeding the
sentinel into a coercer (which crashed the decimal cast).
