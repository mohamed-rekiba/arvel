# HTTP Client

A small, async, fluent client for calling other services — the `Http` facade (Laravel `Http`
parity), built on [httpx](https://www.python-httpx.org). It returns a real `httpx.Response`, so the
full httpx surface is available. httpx is part of the core (no extra needed).

```python
from arvel import Http

response = await Http.get("https://api.example.com/users")
data = response.json()                       # httpx.Response
```

## Verbs

```python
await Http.get(url, params={"page": 2})
await Http.post(url, json={"name": "Ada"})
await Http.put(url, json={...})
await Http.patch(url, json={...})
await Http.delete(url)
```

Each call returns an `httpx.Response` — use `.status_code`, `.json()`, `.text`, `.content`,
`.headers`.

## Configuring a request

Chain builders before the verb; each returns a fresh, configurable request:

```python
await Http.with_token("secret").post(url, json=payload)          # Authorization: Bearer secret
await Http.with_headers({"X-App": "arvel"}).get(url)
await Http.base_url("https://api.example.com/v1").get("/users")  # relative path joins the base
await Http.timeout(5).get(url)                                   # seconds (default 30)
```

They compose: `await Http.base_url(base).with_token(t).timeout(10).get("/me")`.

## Passing httpx options

Any keyword you pass to a verb is forwarded to httpx — e.g. follow redirects (off by default; image
CDNs and many APIs 302 to the real resource):

```python
response = await Http.timeout(15).get(url, follow_redirects=True)
```

## Testing without the network

The client takes an httpx **transport**, so a test can stub responses with no real I/O. Bind a
client with a `MockTransport` behind the `http` service (the `Http` facade resolves it):

```python
import httpx
from arvel.client import Client

def handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"id": 1})

app.instance("http", Client(transport=httpx.MockTransport(handler)))
# code under test that calls `await Http.get(...)` now hits the stub
```

## See also

- [Facades](facades.md) — how `Http` resolves the `http` service.
- [Queues & Jobs](queues.md) — wrap a flaky outbound call in a retrying job.
- [Telemetry](telemetry.md) — outbound calls emit a client span automatically when tracing is on.
