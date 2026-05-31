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

## The `Context` facade

For the common case — stashing request-scoped values that any layer can read without
threading them through call signatures — use the `Context` facade. `ContextMiddleware`
binds a fresh repository per request and flushes it when the request ends, so values never
leak into the next request.

```python
from arvel.facades import Context

Context.add("request_id", "req-abc")
Context.add("tenant_id", "acme")

# Anywhere downstream — no argument passing
Context.get("tenant_id")        # "acme"
Context.has("request_id")       # True
Context.all()                   # {"request_id": "req-abc", "tenant_id": "acme"}
```

`request_id` is set automatically by the observability middleware, and `user_id` is set once
authentication resolves the current user. Every log line emitted during the request carries
these fields — see [Logging](logging.md).

### Hidden keys

Values added with `add_hidden` are readable via `get_hidden` but never appear in `all()` and
are never serialized. Use this for tokens or internal IDs that must not reach logs or queues:

```python
Context.add_hidden("upstream_token", token)
Context.get_hidden("upstream_token")   # token
Context.all()                          # token is absent
```

### Carrying context to queued jobs

`dehydrate()` returns the visible keys (hidden keys excluded) so you can ship them in a job
payload; `hydrate()` restores them in the worker:

```python
payload = Context.dehydrate()       # {"request_id": ..., "tenant_id": ...}
# ... in the worker ...
Context.hydrate(payload)
```

## Deferred work

`defer(fn)` queues a callback to run after the response is sent but before the ASGI scope
closes — handy for fire-and-forget work that shouldn't add latency to the response.
`DeferredTaskMiddleware` drains the queue; a callback that raises is logged and the rest
still run.

```python
from arvel.context import defer

defer(lambda: audit_log.write(...))
```

## Running tasks concurrently

`Concurrency.run` awaits a batch of zero-argument coroutines and returns their results in
order. If one raises, the exception propagates — no failure is silently swallowed.

```python
from arvel.context import Concurrency

prices, stock = await Concurrency.run([
    lambda: fetch_prices(ids),
    lambda: fetch_stock(ids),
])
```

Use `Concurrency.defer(tasks)` to start the batch as a background `asyncio.Task` you await
later.

## Propagation across queued jobs

`contextvars` do NOT survive the boundary between a job dispatcher and a queue worker. If a job needs a context value, **encode it in the job payload** (or use `Context.dehydrate()`/`hydrate()` above):

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
