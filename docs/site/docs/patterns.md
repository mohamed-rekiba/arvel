# Domain Services & Read/Write Split

Some operations need to validate a resource exists through a read model (e.g. a materialized view like `PublishedProduct`), then acquire a write lock on the underlying row (e.g. `Product`) to mutate it safely. Doing the two steps in the wrong order — or skipping one — causes either stale reads or unnecessary lock contention.

`DomainService` encodes this pattern as a reusable base class.

## The pattern

```python
from arvel.database import DB, DomainService
from app.models import Product, PublishedProduct

class StockService(DomainService[PublishedProduct, Product]):
    read_model = PublishedProduct   # visibility check (no lock)
    write_model = Product           # write lock target
```

Call `get_for_write(pk)` **inside** a `DB.transaction()` block:

```python
async with DB.transaction():
    product = await StockService.get_for_write(product_id)
    if product.stock_qty < qty:
        raise InsufficientStockError(product_id)
    product.stock_qty -= qty
    await product.save()
```

## What happens inside `get_for_write`

1. Asserts an active transaction is open (raises `OutsideTransactionError` if not).
2. Calls `read_model.find(pk)` — a fast, unlocked visibility check.
   - If the read model returns `None`, raises `ReadModelNotFoundError` immediately.
     No write lock is acquired, so there's no wasted contention.
3. Issues `SELECT … FOR UPDATE` on `write_model` to acquire the write lock.
4. Returns the locked write-side instance.

## Why this order matters

| Without the pattern | With `DomainService` |
|---|---|
| Checkout resolves `Product` directly | Resolves `PublishedProduct` first |
| Stock can be decremented for unpublished / deleted products | `ReadModelNotFoundError` raised before the lock |
| Write lock acquired even if product is invisible | Lock only acquired when the resource is visible |

## Error handling

```python
from arvel.database import OutsideTransactionError, ReadModelNotFoundError

try:
    async with DB.transaction():
        product = await StockService.get_for_write(product_id)
        ...
except ReadModelNotFoundError:
    raise HTTPException(404, "Product not available")
except OutsideTransactionError:
    # Programming error — fix the call site, not a runtime condition
    raise
```

## Concurrency

Two concurrent requests for the same product race on `SELECT … FOR UPDATE`. SQLAlchemy (via asyncpg) serialises them: one waits while the other holds the lock. Both run inside their own `DB.transaction()` block, so each gets a consistent view.

## Constraints

- Must be called inside `DB.transaction()`. Calling it without a transaction raises
  `OutsideTransactionError` immediately — this is a programming error, not a runtime condition.
- `read_model` and `write_model` are class attributes; they're resolved at call time, not at class definition time, so forward references work.
- If the `write_model` row is missing while the `read_model` row exists (materialized view lag), a second `ReadModelNotFoundError` is raised.

## Importing

```python
from arvel.database import DomainService, OutsideTransactionError, ReadModelNotFoundError
```
