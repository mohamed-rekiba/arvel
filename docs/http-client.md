# HTTP Client

A small, async, fluent client for calling other services — the `Http` facade, built on
[httpx](https://www.python-httpx.org). httpx is part of the **core** — nothing to install.

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

### Exceptions

The client raises its **own** exceptions — it never leaks the underlying httpx type (the same way
it wraps the response in `ClientResponse`):

| Exception | When |
|-----------|------|
| `RequestFailed` | A response arrived with a 4xx/5xx status — via `.throw()`, or an exhausted `retry()`. `.response` is the `ClientResponse`. |
| `RequestTimedOut` | The request exceeded its connect/read timeout. A subclass of `TransportFailed`. |
| `TransportFailed` | The request couldn't complete at the transport level — connection refused, DNS/TLS failure, too-many-redirects, decode error. The original engine exception is on `__cause__`. |

```python
from arvel.client import RequestTimedOut, TransportFailed

try:
    response = await Http.timeout(5).get(url)
except RequestTimedOut:
    ...   # timed out
except TransportFailed:
    ...   # any other transport failure (connection/DNS/TLS)
```

## Passing httpx options

Any keyword you pass to a verb is forwarded to httpx, and a per-call keyword always wins over the
builder's state — e.g. redirects (followed by default) can be disabled for one request:

```python
response = await Http.timeout(15).get(url, follow_redirects=False)  # keep the 302
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

## Streaming Server-Sent Events — `Http.stream`

For `text/event-stream` APIs (LLM token streams, live feeds), `Http.stream(method, url, **kwargs)`
yields parsed `ServerSentEvent`s as they arrive — the body is never fully buffered. It returns an
async generator, so **don't `await` it** — iterate with `async for`:

```python
async for event in Http.base_url("https://api.example.com").with_token(key).stream(
    "POST", "/v1/chat/completions", json={"model": "…", "messages": [...], "stream": True}
):
    if event.data == "[DONE]":
        break
    chunk = json.loads(event.data)   # event.data is the payload after `data:`
    ...
```

- Each `ServerSentEvent` has `.data` (payload; multiple `data:` lines are joined with `\n`),
  `.event` (type, default `"message"`), `.id`, and `.retry`. Comment lines (`:` keep-alives) are
  skipped; the event dispatches on a blank line.
- `Accept: text/event-stream` is set for you (override via `with_headers`/`headers=`).
- A **4xx/5xx** status raises `RequestFailed` (the body is read first, so `exc.response` carries
  status/headers/body); a mid-stream transport failure raises `RequestTimedOut`/`TransportFailed`
  like any other request — wrap the `async for` to map them.
- `retry()` is **not** applied to a stream (a half-consumed body can't be transparently retried);
  wrap the whole `async for` yourself for reconnection. Streams aren't span-wrapped.
- Fake it like any other request — `Http.fake({url: Http.response(body="data: {...}\n\ndata: [DONE]\n\n")})`.

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

## Common mistakes & gotchas

- **Expecting an `httpx.Response`.** A verb returns a `ClientResponse`, not the raw httpx object.
  Use its accessors (`.status()`, `.json()`), or reach the full httpx surface via `.raw`.
- **A `404` that doesn't raise.** Only retry-worthy statuses raise once attempts are exhausted; a
  non-retryable bad status is returned as-is. Call `.throw()` (or `.failed()`) when you want a `4xx`
  to become an exception.
- **Expecting to see the `3xx` itself.** Redirects are followed by default (an API/CDN that 302s
  to the real resource just works) — call `.without_redirects()` or pass `follow_redirects=False`
  when the redirect response is the thing you're asserting on.
- **Treating a `pool` slot as a response.** A failed slot holds the *exception object*, not raised —
  check `isinstance(slot, Exception)` before using it.
- **A stray real request in a test.** Under `Http.fake`, an unmatched URL passes through to the real
  network unless you call `Http.prevent_stray_requests()`. Set it so a missed stub fails loudly.

## See also

- [Facades](facades.md) — how `Http` resolves the `http` service.
- [Queues & Jobs](queues.md) — wrap a flaky outbound call in a retrying job.
- [Telemetry](telemetry.md) — outbound calls emit a client span automatically when tracing is on
  (real sends **and** faked ones — the W3C `traceparent` is injected either way).
