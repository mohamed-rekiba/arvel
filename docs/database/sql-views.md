# SQL Views & Functions

## Views & materialized views

Declare **views** and **materialized views** as classes, then create them in a migration; a
read-only model reads from a view and **rejects writes**:

```python
from arvel.database.schema import View, MaterializedView

class ActiveUsers(View):
    name  = "active_users"
    query = User.where(active=True).select("id", "name")

class MonthlyRevenue(MaterializedView):
    name = "monthly_revenue"
    query = Order.select("month", "revenue")
    refresh = "concurrently"

class ActiveUser(Model):
    __view__ = "active_users"        # read-only: save()/delete()/touch() raise ReadOnlyModelError

await MonthlyRevenue().refresh_op()  # refresh the MV
```

## Stored functions

Call a stored database function (injection-safe — the name goes through SQLAlchemy's `func`
registry, never string-interpolated):

```python
balance = await db.call_function("increment_balance", account_id=7, amount=100)
```
