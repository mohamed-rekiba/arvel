# ADR-035: Streaming and Chunking Completeness

Status: Accepted

Eloquent-parity increment (backlog `005`, Sprint B: story S10). No HTTP or schema
surface — recorded as an ADR.

## ADR-035-01: `stream()` is a true server-side cursor, distinct from `lazy()`

Status: Accepted

`lazy()` / `cursor()` walk a keyset in `LIMIT` batches — stable under concurrent writes
but issues N queries. `stream()` is the other tool: one statement, fetched incrementally
from the driver via SQLAlchemy `AsyncSession.stream_scalars()` with `yield_per`. It fires
`retrieved` per row and does **not** batch-eager-load pivot relations (there's no batch) —
use `lazy()`/`chunk()` when you need pivot eager-loading while streaming.

## ADR-035-02: Directional keyset — `descending=` on `chunk_by_id`, plus `lazy_by_id`

Status: Accepted

Keyset iteration gains a direction. `chunk_by_id(..., descending=True)` and the new
`lazy_by_id(..., descending=True)` order by the key column `DESC` and page with `col <
last` instead of `col > last`. `lazy()` stays the ascending shorthand. A shared
`_keyset_batches(size, column, descending)` generator backs `chunk_by_id`, `lazy`, and
`lazy_by_id` so the walk logic lives in one place.

## ADR-035-03: Callbacks can stop early by returning `False`

Status: Accepted

`chunk` / `chunk_by_id` / `each` callbacks may return `False` to stop iteration, matching
Eloquent. Returning `None` (or anything truthy) continues. Signatures widen to
`Awaitable[bool | None]`.

## ADR-035-04: Offset `chunk` enforces an order by primary key

Status: Accepted

Offset pagination without a stable order can skip or repeat rows. Rather than raise (the
base-query-builder behaviour), Arvel's model-bound builder follows Eloquent: if no
`order_by` is set, `chunk` (and `each`, which delegates to it) auto-orders by the model's
primary key. An explicit `order_by` is respected as-is.
