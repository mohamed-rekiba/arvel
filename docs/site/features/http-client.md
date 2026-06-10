# HTTP Client

<a name="introduction"></a>
## Introduction

Arvel ships a small, fluent wrapper around [`httpx`](https://www.python-httpx.org/) so you can make outbound HTTP requests without reaching for the raw client every time. The `Http` facade handles the common cases — headers, auth, timeouts, JSON — and gives you a testing fake that records and stubs requests so your tests never touch the network.

The facade is stateless: every builder method returns a fresh request, so there's nothing to bind or reset between calls.

```python
from arvel.facades import Http

resp = await Http.accept_json().get("https://api.example.com/users")
if resp.successful():
    users = resp.json()
```

<a name="quick-start"></a>
### Quick start

```python
from arvel.facades import Http

# Outbound call
resp = await Http.with_token(token).accept_json().get("https://api.example.com/me")
if resp.failed():
    resp.raise_for_status()
profile = resp.json()

# Test without network I/O
with Http.fake({"api.example.com/*": Http.response({"id": 1}, 200)}):
    resp = await Http.get("https://api.example.com/users/1")
    assert resp.json() == {"id": 1}
    Http.assert_sent_count(1)
```

| Need | API |
|---|---|
| JSON API with auth | `Http.with_token(...).accept_json().get/post(...)` |
| Form body instead of JSON | chain `.as_form()` before `post` / `put` / `patch` |
| Relative paths against a base | `.base_url("https://api.example.com/v1").get("users")` |
| Stub + assert in tests | `Http.fake(stubs)` — see [Testing](#testing) and [Testing](testing.md#faking-services) |

> [!NOTE]
> `Http` is always available — no service provider to register. See [Facades](../core-concepts/facades.md#quick-start).

<a name="making-requests"></a>
## Making Requests

Each verb is an `async` method that sends the request and returns a [`Response`](#responses). Use the bare verb for a simple call, or chain builder methods first.

```python
# GET with query params
resp = await Http.get("https://api.example.com/users", {"page": 2})

# POST JSON (the default body format)
resp = await Http.post("https://api.example.com/users", {"name": "Sara"})

# Other verbs
await Http.put(url, {"name": "Sara"})
await Http.patch(url, {"name": "Sara"})
await Http.delete(url)
await Http.head(url)
```

`post`, `put`, `patch`, and `delete` send their `data` as JSON unless you switch to form encoding with [`as_form()`](#request-options).

<a name="request-options"></a>
### Request Options

Builder methods return a `PendingRequest`, so chain as many as you need before the verb:

```python
resp = (
    await Http.with_token("secret-token")
    .accept_json()
    .timeout(5.0)
    .base_url("https://api.example.com/v1")
    .get("users")
)
```

| Method | What it does |
|---|---|
| `with_headers({...})` | Merge extra request headers |
| `with_token(token, scheme="Bearer")` | Set `Authorization: <scheme> <token>` |
| `with_basic_auth(user, password)` | Set HTTP basic auth |
| `accept(content_type)` | Set the `Accept` header |
| `accept_json()` | Shorthand for `accept("application/json")` |
| `as_form()` | Send the body as `application/x-www-form-urlencoded` instead of JSON |
| `timeout(seconds)` | Per-request timeout |
| `base_url(url)` | Prefix relative paths; absolute URLs ignore it |

`base_url` joins like Laravel: a relative path (`"users"`) is appended to the base, while an absolute URL (`"https://other.test/x"`) is sent as-is.

<a name="responses"></a>
## Responses

`Response` wraps the underlying `httpx.Response` with Laravel-style predicates and accessors.

```python
resp = await Http.get("https://api.example.com/users")

resp.status()        # 200
resp.ok()            # status == 200
resp.successful()    # 2xx
resp.redirect()      # 3xx
resp.client_error()  # 4xx
resp.server_error()  # 5xx
resp.failed()        # >= 400

resp.json()          # decoded JSON body
resp.body()          # raw text
resp.header("x-id")  # single header, or None
resp.headers()       # dict of all headers
resp.raw             # the underlying httpx.Response
```

Call `resp.raise_for_status()` to raise on a 4xx/5xx (it returns the response so you can chain).

<a name="testing"></a>
## Testing

`Http.fake()` is a context manager that intercepts every outbound request for its duration. With no stubs, every request gets an empty `200` — so tests never hit the network by accident.

```python
async def test_fetches_user() -> None:
    with Http.fake({"api.example.com/*": Http.response({"id": 1}, 200)}):
        resp = await Http.get("https://api.example.com/users/1")

    assert resp.json() == {"id": 1}
```

<a name="stubbing-responses"></a>
### Stubbing Responses

Pass a dict of glob patterns to stubbed responses. The first matching pattern wins, and the URL is matched both with and without its scheme, so `api.example.com/*` and `https://api.example.com/*` both work. Use `*` to match everything.

```python
stubs = {
    "api.example.com/users/*": Http.response({"id": 1}),
    "*": Http.response("not found", status=404),
}
with Http.fake(stubs):
    ...
```

`Http.response(body=None, status=200, headers=None)` builds the stub. A `dict`/`list` body is sent as JSON; a `str`/`bytes` body is sent as raw content; `None` is an empty body.

<a name="inspecting-requests"></a>
### Inspecting Requests

The fake records every request. Bind it with `as fake` to read them, or use the assertion helpers on the facade.

```python
with Http.fake() as fake:
    await Http.with_token("abc").post("https://api.example.com/orders", {"qty": 2})

    Http.assert_sent(lambda r: r.method == "POST" and r.data == {"qty": 2})
    Http.assert_sent(lambda r: r.has_header("authorization", "Bearer abc"))
    Http.assert_sent_count(1)

    # Or read the recorded requests directly
    assert fake.recorded[0].url == "https://api.example.com/orders"
```

| Helper | Asserts |
|---|---|
| `Http.assert_sent(predicate)` | At least one recorded request matches |
| `Http.assert_not_sent(predicate)` | No recorded request matches |
| `Http.assert_sent_count(n)` | Exactly `n` requests were sent |
| `Http.assert_nothing_sent()` | No requests were sent |
| `Http.recorded()` | The list of `RecordedRequest`s |

A `RecordedRequest` exposes `method`, `url`, `headers`, `params`, `data`, and a `has_header(name, value=None)` helper. The assertion helpers raise `TypeError` if called outside an active `Http.fake()` context.
