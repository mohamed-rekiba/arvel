# WI-arvel-046 — `response()` / `redirect()` HTTP helpers

- **Module:** 46 (HTTP — response builders)
- **Complexity:** L2
- **Risk tier:** 2
- **Data classification:** internal
- **Status:** completed

A WI-043 bucket-3 feature gap. Laravel devs reach for `response()` and
`redirect()`; Arvel had neither, so handlers built Starlette responses by hand
and there was no ergonomic redirect-with-session-flash.

## Scope

New module `arvel/http/responses.py`, re-exported from `arvel.http`. No changes
to the request path or existing response handling — handlers can still return a
`dict`, model, or any Starlette `Response`. These are additive helpers.

## What landed

### `response()` — builder factory

```python
response().json(data, status=201)
response().text("pong")
response().make(b"raw", headers={...})
response().no_content()            # 204
```

`response()` returns a shared stateless `ResponseFactory`.

### `redirect()` and friends

```python
redirect("/dashboard")               # 302
redirect("/dashboard", status=301)
to_route("users.show", id=7)         # named route -> /users/7 via routing.route
back(request, fallback="/")          # Referer header
```

`redirect()` returns a `Redirect` (a `RedirectResponse` subclass) so it can flash:

```python
redirect("/posts").with_(request, status="Post created!")
```

`with_(request, **values)` flashes each value into `request.state.session` and
returns `self` (chainable). It's a no-op when the session middleware isn't active
on the route, so it's safe to call unconditionally.

## Design notes

- **No new global state.** Flash needs the session, which lives on
  `request.state.session`, so `with_` and `back` take the request explicitly
  rather than introducing a current-request `ContextVar`.
- **No import cycle.** `to_route` imports `arvel.routing` lazily inside the
  function — `routing` is a heavy module and importing it at module load would
  risk a cycle through the HTTP layer.
- **Thin on purpose.** `response()` builders wrap Starlette responses 1:1; the
  real value-add is discoverability + the flash-aware redirect.

## Tests

`packages/arvel/tests/http/test_wi046_response_redirect.py` — 12 cases:
factory builders (json/text/make/no_content + singleton), redirect status +
Location, `with_` flash round-trip (flash → finalize → get) and no-session
no-op, `back` via Referer and fallback, `to_route` named-route URL.

## Gates

ruff check + format clean; `uv run mypy` 0 issues (1069 files); `uv run pyright`
0 errors / 0 warnings; http suite 209 passed; mkdocs build --strict clean.
