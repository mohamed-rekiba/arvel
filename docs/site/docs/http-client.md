# HTTP Client

For talking to external HTTP APIs, Arvel ships a thin facade over [`httpx`](https://www.python-httpx.org/) — the modern, async-native Python HTTP client. The `Http` facade gives you a fluent, Laravel-like wrapper with retries, response macros, and fakes for testing.

## Basic requests

```python
from arvel.facades import Http


response = await Http.get("https://api.example.com/users")
data = response.json()
status = response.status_code
```

All verbs are available: `get`, `post`, `put`, `patch`, `delete`, `head`.

## Sending request bodies

```python
# JSON body
response = await Http.post(
    "https://api.example.com/users",
    json={"name": "Alice", "email": "alice@example.com"},
)

# Form-encoded body
response = await Http.post(
    "https://api.example.com/login",
    data={"username": "alice", "password": "..."},
)

# Multipart
response = await Http.post(
    "https://api.example.com/upload",
    files={"avatar": ("face.png", png_bytes, "image/png")},
)
```

## Headers

```python
response = await (
    Http
    .with_headers({"X-Trace-Id": "abc"})
    .with_token("Bearer eyJhbGciOi...")
    .get("https://api.example.com/me")
)
```

`with_token(...)` is shorthand for `with_headers({"Authorization": ...})`.

## Retries

```python
response = await (
    Http
    .retry(times=3, sleep_ms=200, backoff="exponential")
    .get("https://flaky.example.com/data")
)
```

Default behavior: retry on connection errors, `5xx`, and `408`/`429`. Customize via `retry_on=[502, 503, 504]`.

## Timeouts

```python
response = await Http.timeout(connect=5.0, read=30.0).get("https://slow.example.com")
```

Always set timeouts. The default is **30 seconds read, 5 seconds connect** — long enough to be useful, short enough to avoid hanging your worker.

## Inspecting responses

```python
response.ok                  # → True if 2xx
response.status_code         # → 200
response.headers["X-Foo"]    # → header value or KeyError
response.json()              # → parsed JSON
response.text                # → str body
response.content             # → bytes body
response.raise_for_status()  # → raises on 4xx/5xx
```

## Pooling connections

`Http` reuses an HTTPX async client per process, so connections are pooled across calls. For a long-lived integration where you want a dedicated client (different defaults, separate connection pool), construct one:

```python
from arvel.http_client import HttpClient


stripe = HttpClient(
    base_url="https://api.stripe.com/v1",
    timeout=30.0,
    headers={"Authorization": f"Bearer {stripe_key}"},
)

response = await stripe.get("/customers/cus_xyz")
```

## Testing with fakes

Don't make real network calls in tests. Use `Http.fake()`:

```python
async def test_fetches_user(client) -> None:
    Http.fake(
        {
            "GET https://api.example.com/users/42": Http.response(
                json={"id": 42, "name": "Alice"},
                status=200,
            ),
        }
    )
    response = await client.get("/proxy/users/42")
    Http.assert_sent(lambda req: req.url == "https://api.example.com/users/42")
```

For wildcard matching:

```python
Http.fake({
    "api.example.com/*": Http.response(json={"ok": True}),
})
```

Any unmocked request raises `UnexpectedHttpRequest`, so accidental network calls fail loudly.

## Where to next?

- [Queues](queues.md) — for expensive external calls that shouldn't block the request.
- [Configuration](configuration.md) — env vars for default timeouts.
