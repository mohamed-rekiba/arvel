# Transactions & Streaming

Atomic units of work, pessimistic locks, raw SQL escape hatches, and memory-safe iteration
over large result sets.

## Transactions, locking, raw

```python
async def transfer(conn):
    ...

await db.transact(transfer)                            # commit on success, rollback on error
row = await Post.where(id=1).lock_for_update().first() # pessimistic lock
rows = await db.select("SELECT * FROM posts WHERE views > :n", {"n": 100})
```


## Streaming large result sets

```python
async for post in Post.where(published=True).lazy(): ...     # streamed, low memory
async for post in Post.cursor(): ...                          # one row at a time
await Post.chunk_by_id(500, handle_chunk)                     # keyset pagination, stable under inserts
```
