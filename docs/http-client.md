# HTTP Client

A small, async, fluent client for calling other services — the `Http` facade (`Http`
parity), built on [httpx](https://www.python-httpx.org). httpx is part of the core (no extra
needed).

```python
from arvel import Http

response = await Http.get("https://api.example.com/users")
data = response.json()                       # ClientResponse
```

## Verbs

```python
await Http.get(url, params={"page": 2})
await Http.post(url, json={"name": "Ada"})
await Http.put(url, json={...})
await Http.patch(url, json={...})
await Http.delete(url)
```

Each call returns a **`ClientResponse`** (below) — not a bare `httpx.Response`. Reach the full
httpx surface via `.raw` (`response.raw.status_code`, `response.raw.headers`, …).

## Configuring a request

Chain builders before the verb; each returns a fresh, configurable request (the chain is
"immutable-ish" — each builder call returns a clone, so it's safe to keep and reuse a partially
configured request, e.g. across the several calls queued inside `Http.pool`):

```python
await Http.with_token("secret").post(url, json=payload)          # Authorization: Bearer secret
await Http.with_headers({"X-App": "arvel"}).get(url)
await Http.base_url("https://api.example.com/v1").get("/users")  # relative path joins the base
await Http.timeout(5).get(url)                                   # seconds (default 30)
await Http.connect_timeout(2).timeout(10).get(url)                # separate connect vs. total timeout
```

They compose: `await Http.base_url(base).with_token(t).timeout(10).get("/me")`.

### Retries

```python
from arvel.client import ClientResponse

# up to 3 total attempts, 100ms between them — retries connect errors and 5xx by default
await Http.retry(3, 100).get(url)

# override the retry policy: only retry on 429 (rate limited); `when` gets the exception
# for a connect/timeout failure, or the ClientResponse for a completed request
await Http.retry(5, 200, when=lambda r: isinstance(r, ClientResponse) and r.status() == 429).get(url)
```

If every attempt is still retry-worthy once attempts are exhausted, `retry()` raises — the last
exception (connect/timeout errors), or `RequestFailed` for a persistent bad-status response. A
status that isn't retry-worthy (e.g. a 404) is returned as-is, not retried and not raised — use
`.throw()` (below) if you want that to raise.

### Forms, multipart, attachments

```python
await Http.as_form().post(url, data={"name": "Ada"})               # application/x-www-form-urlencoded

await (
    Http.as_multipart()
    .attach("avatar", png_bytes, filename="avatar.png", headers={"Content-Type": "image/png"})
    .post(url, data={"caption": "profile photo"})
)
```

### Content negotiation + raw bodies

```python
await Http.accept_json().get(url)                # Accept: application/json
await Http.accept("text/csv").get(url)
await Http.with_body("<xml/>", "application/xml").post(url)   # bypasses json/data/files entirely
```

### Auth

```python
await Http.with_token("secret").get(url)                     # Authorization: Bearer secret
await Http.with_token("secret", scheme="Token").get(url)      # Authorization: Token secret
await Http.with_basic_auth("ada", "s3cret").get(url)          # Authorization: Basic <base64>
await Http.with_digest_auth("ada", "s3cret").get(url)         # httpx.DigestAuth — completes the
                                                               # 401 challenge/response handshake
```

## The response wrapper — `ClientResponse`

```python
response = await Http.get(url)

response.status()          # int
response.body()            # str
response.json()            # parsed JSON (or `default=` if the body isn't valid JSON)
response.json("user.name") # dotted-key lookup into the parsed JSON
response.header("ETag")    # str | None
response.headers()         # httpx.Headers

response.ok()               # exactly 200
response.successful()       # any 2xx
response.redirect()         # 3xx
response.client_error()     # 4xx
response.server_error()     # 5xx
response.failed()           # client_error() or server_error()

response.throw()            # raises RequestFailed(response) if failed(); else returns self (chainable)
(await Http.get(url)).throw().json()
```

`RequestFailed.response` is the `ClientResponse`, so a handler can inspect `.status()`/`.body()`.

## Passing httpx options

Any keyword you pass to a verb is forwarded to httpx — e.g. follow redirects (off by default; image
CDNs and many APIs 302 to the real resource):

```python
response = await Http.timeout(15).get(url, follow_redirects=True)
```

## Concurrent requests — `Http.pool`

```python
responses = await Http.pool(
    lambda pool: [
        pool.get(url_a),
        pool.as_form().post(url_b, data={"x": 1}),
        pool.get(url_c),
    ]
)
# one shared connection; ordered results matching the callback's list.
# a failed slot holds the *exception object*, not raised — check with isinstance(slot, Exception).
```

## Testing without the network

### `Http.fake` (recommended — no app wiring needed)

```python
with Http.fake({"https://api.example.com/*": Http.response(body={"id": 1}, status=201)}):
    response = await Http.post("https://api.example.com/users", json={"name": "Ada"})
    assert response.status() == 201

    Http.assert_sent(lambda r: r.method == "POST" and "users" in r.url)
    Http.assert_not_sent(lambda r: r.method == "DELETE")
    Http.assert_sent_count(1)
```

- Keys are URL patterns with `*` wildcards (matched against the **full URL**, e.g.
  `"*.example.com/*"`).
- A value is either a `Http.response(body=..., status=200, headers=None)` stub, or a callable
  `(request) -> stub` for a dynamic response (`request` is a `RecordedRequest`: `.method`, `.url`,
  `.headers`, `.content`, `.json(key=None, default=None)`).
- `Http.fake()` with no mapping stubs *every* request with a generic 200.
- An unmatched URL passes through to the real network — unless `Http.prevent_stray_requests()` is
  set, in which case it raises `StrayRequest`.
- `Http.fake(...)` is both a context manager (auto-restores on exit) and a plain call — pair the
  latter with an explicit `Http.restore()`.
- `Http.recorded(predicate=None)` returns the list of `RecordedRequest` captured since the last
  `fake()` call (empty when no fake is active).

### Swapping the transport directly

The client also takes a raw httpx **transport**, if you'd rather bind a stub client into the
container yourself:

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
- [Telemetry](telemetry.md) — outbound calls emit a client span automatically when tracing is on
  (real sends **and** faked ones — the W3C `traceparent` is injected either way).
