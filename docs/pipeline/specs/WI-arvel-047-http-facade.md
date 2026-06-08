# WI-arvel-047 — `Http` facade + `Http.fake` (outbound HTTP client)

- **Module:** 47 (HTTP — outbound client)
- **Complexity:** L2
- **Risk tier:** 2
- **Data classification:** internal
- **Status:** completed

A WI-043 bucket-3 feature gap, flagged high impact / large effort. Apps called
`httpx` directly, so there was no first-party client API and no way to fake
outbound HTTP in tests. This adds a Laravel-style `Http` facade plus a recording
fake.

## Scope

Three new modules, re-exported from `arvel.facades`:

- `arvel/http/client.py` — the engine (`PendingRequest`, `Response`, the fake hook).
- `arvel/facades/http.py` — the stateless `Http` facade.
- `arvel/testing/fakes/http.py` — `HttpFake`, `FakeResponse`, `HttpFakeContext`.

No runtime dependency from the client on the testing package: the fake hook is a
`ContextVar[FakeTransport | None]` in `client.py`, and the testing package
installs an `HttpFake` into it.

## What landed

### Requests

```python
resp = (
    await Http.with_token("tok")
    .accept_json()
    .timeout(5.0)
    .base_url("https://api.example.com/v1")
    .get("users", {"page": 2})
)
```

`PendingRequest` builders: `with_headers`, `with_token(token, scheme="Bearer")`,
`with_basic_auth`, `accept`, `accept_json`, `as_form`, `timeout`, `base_url`.
Async verbs: `get`, `head`, `post`, `put`, `patch`, `delete`. Bodies are JSON by
default; `as_form()` switches to form encoding. `base_url` prefixes relative
paths and is ignored for absolute URLs.

### Responses

`Response` wraps `httpx.Response`: `status`, `ok`, `successful`, `redirect`,
`failed`, `client_error`, `server_error`, `json`, `body`, `header`, `headers`,
`raise_for_status` (returns self), and `raw`.

### Testing

```python
with Http.fake({"api.example.com/*": Http.response({"id": 1}, 200)}) as fake:
    resp = await Http.get("https://api.example.com/users/1")
    Http.assert_sent(lambda r: r.method == "GET")
    assert fake.recorded[0].url.endswith("/users/1")
```

`Http.fake(stubs)` installs an `HttpFake` for the block. Stubs are glob patterns
matched with and without the scheme; the first match wins; unmatched requests
get an empty `200` so a fake never reaches the network. `Http.response(body,
status, headers)` builds a stub (dict/list → JSON, str/bytes → raw, None →
empty). Assertions: `recorded`, `assert_sent`, `assert_not_sent`,
`assert_sent_count`, `assert_nothing_sent` (raise `TypeError` outside a fake).

## Design notes

- **No runtime coupling to tests.** The client only knows about a
  `FakeTransport` Protocol and a `ContextVar`; the fake lives in the testing
  package and is `ContextVar`-scoped so concurrent tests don't bleed.
- **`OutboundRequest` dataclass.** The fake's `handle` took six args (PLR0913);
  grouping them into a frozen `OutboundRequest` cleans up both the Protocol and
  the call site.
- **Token typing.** `set_fake` returns `Token[FakeTransport | None]` and
  `reset_fake` takes it back — no `isinstance(token, Token)` dance.
- **JSON boundary cast.** Stub bodies are arbitrary JSON; the `else` branch in
  `FakeResponse.build` casts from `object` (not a narrowed `dict[Unknown, ...]`)
  to `Any` for httpx's `json=`, keeping pyright clean without suppressions.

## Tests

`packages/arvel/tests/http/test_wi047_http_facade.py` — 18 cases: `Response`
predicates and `raise_for_status`; `base_url` relative-join and absolute-ignore
(asserted via the fake's recorded URL); fake basics (no-stub empty-200, JSON
stub, pattern match + default fallback); request recording (method, URL, data,
headers); and every assertion helper.

## Gates

ruff check + format clean; `uv run mypy` 0 issues (1073 files); `uv run pyright`
0 errors / 0 warnings; http suite 227 passed; mkdocs build --strict clean.
