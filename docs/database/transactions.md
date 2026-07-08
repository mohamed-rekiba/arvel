# Transactions & Streaming

Two problems the ORM handles at the connection level, below the query builder: keeping a group of
writes **all-or-nothing**, and reading a **large result set** without loading it all into memory at
once. Both go through the `db` connection manager (`app.make("db")`, or the `DB` facade), so they
compose with everything the builder does — a model save inside a transaction rolls back with it, a
streamed query honors your `where`/`order` clauses.

The examples below use a `db` handle — resolve it with `db = app.make("db")`, take it as a
constructor dependency, or reach for the `DB` facade (`DB.transaction()`), whichever fits the layer
you're in.

## Transactions

Wrap a unit of work in `db.transaction()` and every write inside it commits together or not at all —
one failure rolls the whole block back:

```python
async with db.transaction():
    account = await Account.find(sender_id)
    account.balance -= amount
    await account.save()

    await Account.where(id=recipient_id).increment("balance", amount)
    await Transfer.create(sender_id=sender_id, recipient_id=recipient_id, amount=amount)
    # commit here, on a clean exit
```

If any statement raises — a constraint violation, a bad lookup, your own `abort()` — the block exits
without committing and the database is left exactly as it was. There's no `try/except` to remember and
no manual `rollback()` to call: leaving the `async with` normally commits, leaving it via an exception
rolls back.

### Nesting: savepoints, not a second BEGIN

Transactions nest. Opening `db.transaction()` while one is already active doesn't start a second
top-level transaction (databases don't have those) — it opens a **savepoint**, so an inner failure
rolls back only the inner block:

```python
async with db.transaction():          # outer
    await Order.create(...)

    try:
        async with db.transaction():  # savepoint
            await charge_card(order)  # if this raises...
    except PaymentError:
        order.status = "unpaid"       # ...only the inner block rolled back;
        await order.save()            #    the order still exists, and this commits with the outer
```

The outermost transaction is the one that actually commits. It also owns the **after-commit buffer**:
events dispatched with `after_commit` and jobs queued inside the block are held until the real
`COMMIT` lands, and dropped entirely if the transaction rolls back — so you never fire an "order
placed" event for an order that didn't persist. See [Events](../events.md) for `after_commit` dispatch.

### The decorator and callback forms

Two shorthands wrap the same machinery. `@db.transactional` runs a whole function in a transaction:

```python
@db.transactional
async def place_order(cart):
    order = await Order.create(customer_id=cart.customer_id, total=cart.total)
    for line in cart.lines:
        await order.items().create(product_id=line.product_id, qty=line.qty)
    return order
```

`db.transact(callback)` is the callback form — useful when you want the connection in hand, or when
you want **automatic retries on a deadlock**:

```python
await db.transact(transfer_funds)                      # commit on success, rollback on error
await db.transact(transfer_funds, attempts=3)          # retry a deadlock/serialization failure
```

`attempts` retries **only transient failures** — a deadlock or serialization conflict, the kind that
succeeds if you just run it again — with a capped exponential backoff between tries. A *permanent*
error (a unique-constraint violation, a type error, bad SQL) raises immediately without burning a
retry, because re-running it would fail identically. The default is a single attempt.

## Pessimistic locking

When two requests read-then-write the same row, the last write can clobber the first. Take a
row-level lock inside a transaction to serialize them:

```python
async with db.transaction():
    seat = await Seat.where(id=seat_id).lock_for_update().first()   # FOR UPDATE
    if seat.taken:
        abort(409, "Seat already booked.")
    seat.taken = True
    await seat.save()
```

- **`lock_for_update()`** — `SELECT … FOR UPDATE`. Other transactions block on this row until yours
  commits. Use it when you'll write the row you read.
- **`shared_lock()`** — `SELECT … FOR SHARE`. Others can still read but can't write until you commit.
  Use it when you need the row to *stay put* while you read related data, but aren't changing it.

Locks only mean anything inside a transaction — a lock on an autocommitted query is released the
instant the statement finishes. SQLite has no row-level lock (it locks the whole database for a
write), so these compile to a plain `SELECT` there; the transaction still serializes writers.

## Raw SQL

The builder covers the common cases; when you need SQL it doesn't express, drop down without leaving
the connection (and its transaction, logging, and telemetry):

```python
rows = await db.select(
    "SELECT id, name FROM users WHERE last_login < :cutoff",
    {"cutoff": cutoff},
)                                                    # list of dict-like rows

await db.statement("REFRESH MATERIALIZED VIEW monthly_revenue")   # INSERT/UPDATE/DDL
```

`db.select` returns mapped rows (dict-like); `db.statement` runs a write or DDL statement and returns
the driver result. **Always pass values as bind parameters** (`:name`) — never format them into the
string — so the driver escapes them and you're safe from SQL injection. Both run on the active
transaction's connection when one is open (so they see your uncommitted writes and roll back with the
block); standalone, `db.statement` commits itself and marks the connection sticky, so a subsequent
read on the same request routes to the primary, not a replica.

## Streaming large result sets

`await Query.get()` materializes every matching row into a list. For a table you *know* is large — an
export, a backfill, a nightly reconciliation — that's a memory spike waiting to happen. Stream instead.

### Iterate one model at a time

`cursor()` (and its alias `lazy()`) opens a server-side cursor and yields hydrated models one by one —
constant memory no matter how many rows match:

```python
async for user in User.where(active=True).lazy():
    await send_digest(user)
```

### Process in batches

When per-row work is cheap but you want to batch a side effect (a bulk API call, a `WHERE IN` write),
page through in chunks. There are two strategies, and the difference matters:

```python
# keyset pagination on the primary key — the safe default
await User.where(active=True).chunk_by_id(500, handle_batch)

# offset pagination — simpler, but rows shifting between pages get skipped/repeated
await User.where(active=True).chunk(500, handle_batch)

# per-row, streamed chunk_size at a time under the hood
await User.where(active=True).each(mark_seen, chunk_size=1000)
```

**Prefer `chunk_by_id`.** It walks the table by `WHERE id > <last>` instead of `LIMIT/OFFSET`, so it's
stable even when rows are inserted or deleted mid-walk — an offset-based `chunk()` shifts every later
page when a row is added, silently skipping or repeating rows. Reach for `chunk()` only on a read-only
snapshot you know isn't changing. All three accept a sync or async callback, and returning `False` from
it stops the walk early:

```python
async def handle_batch(users):
    await mailer.send_bulk(users)
    if quota_exceeded():
        return False        # stop paging
```

`chunk_by_id` keys off the model's primary key by default; pass `column=` to page by a different
ordered column. Because it uses keyset pagination, it works for string and UUID primary keys, not just
integers.

## Common mistakes & gotchas

- **Locking outside a transaction does nothing.** `lock_for_update()` on a bare query releases the
  lock as soon as the statement returns. Wrap the read *and* the write in one `db.transaction()`.
- **Retrying a permanent error.** `attempts=` only helps deadlocks and serialization failures. A
  unique-constraint violation fails identically every time — `transact` correctly raises it on the
  first try instead of retrying.
- **`chunk()` on a live table.** Offset paging skips or repeats rows when the table changes under you.
  Use `chunk_by_id` for anything being written concurrently.
- **`get()` on a big export.** Materializes the whole result set into memory. Switch to `lazy()` /
  `cursor()` for an unbounded read.
- **Manual `rollback()`.** You don't call it — raising inside the block rolls back; returning commits.

## How it works

`db.transaction()` is an async context manager over the connection's `engine.begin()`. It tracks the
active connection in a `ContextVar`, so a nested call sees the open transaction and issues
`begin_nested()` (a `SAVEPOINT`) instead of a second `BEGIN`. The outermost frame additionally enters
the event dispatcher's transaction context *outside* `engine.begin()`, so the after-commit buffer
flushes strictly after the real `COMMIT` and is discarded on rollback. Streaming reads
(`cursor`/`lazy`/`stream`) use SQLAlchemy's server-side cursor (`.stream()`); `chunk_by_id` rewrites
the builder's `where`/`order`/`limit` per page and restores them on exit, so the builder is left
untouched for reuse.

## See also

- [Queries](queries.md) — the builder these streaming and locking methods hang off.
- [Events](../events.md) — `after_commit` dispatch and the transaction buffer.
- [Console](../console.md) — long-running commands (backfills, pruning) that stream over big tables.
- [Telemetry](../telemetry.md) — each statement is traced as a `db <OP>` span (statement only, never
  bind values).
