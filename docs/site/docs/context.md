# Context

Arvel uses Python's `contextvars` for per-request and per-task state — the same primitive Starlette, FastAPI, and `httpx` use internally.

## Reading request-scoped state

```python
from arvel.facades import Request, Auth, Container

# Inside a route handler — always valid
request = Request.current()
user = Auth.user()
container = Container.current()
```

These accessors are backed by `ContextVar` and propagate through `asyncio.gather`, `TaskGroup`, and `run_in_executor` (provided you use `contextvars.copy_context`).

## Defining your own context variable

```python
from contextvars import ContextVar

current_tenant: ContextVar[str | None] = ContextVar("current_tenant", default=None)


# Middleware sets it
@app.middleware("http")
async def tenant_middleware(request, call_next):
    tenant = request.headers.get("X-Tenant-Id")
    token = current_tenant.set(tenant)
    try:
        return await call_next(request)
    finally:
        current_tenant.reset(token)


# Anywhere downstream
def get_tenant():
    return current_tenant.get()
```

## Propagation across queued jobs

`contextvars` do NOT survive the boundary between a job dispatcher and a queue worker. If a job needs a context value, **encode it in the job payload**:

```python
class SendInvoice(Job):
    invoice_id: int
    tenant_id: str   # carry context explicitly

    async def handle(self) -> None:
        token = current_tenant.set(self.tenant_id)
        try:
            ...
        finally:
            current_tenant.reset(token)
```

## See also

- [Requests](requests.md) — the request lifecycle and middleware hooks.
- [Queues](queues.md) — how jobs cross process boundaries.
