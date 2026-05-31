"""Request-scoped context: ``Context``, ``defer()``, and ``Concurrency``.

```python
from arvel.context import Context, defer, Concurrency

Context.add("tenant_id", "acme")
Context.get("tenant_id")          # "acme"
Context.add_hidden("token", "…")  # never serialized, never in all()

defer(lambda: cleanup())          # runs after the response is sent

await Concurrency.run([fetch_a, fetch_b])
```
"""

from __future__ import annotations

from arvel.context.concurrency import Concurrency, Task
from arvel.context.facade import Context, defer
from arvel.context.middleware import ContextMiddleware, DeferredTaskMiddleware
from arvel.context.repository import (
    ContextRepository,
    bind_repository,
    current_repository,
    reset_repository,
)

__all__ = [
    "Concurrency",
    "Context",
    "ContextMiddleware",
    "ContextRepository",
    "DeferredTaskMiddleware",
    "Task",
    "bind_repository",
    "current_repository",
    "defer",
    "reset_repository",
]
