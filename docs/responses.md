# Responses

Every route handler returns a response. Most of the time you return a plain value and arvel does
the right thing; when you need control over status, headers, redirects, or file downloads, the
`response` and `redirect` helpers are there.

## Returning data

Return a `dict` (or a list, or any JSON-serializable value) and arvel sends JSON with a `200`:

```python
async def index(request):
    return {"users": [...]}          # → 200 application/json
```

Return a typed object (a msgspec struct) and arvel serializes it **and** generates the OpenAPI
response schema for the route:

```python
async def show(request) -> UserOut:
    return UserOut(id=1, name="Ada")  # typed → response schema at /schema
```

Return a [view](views.md) for HTML:

```python
async def home(request):
    return await view("welcome", {...}).to_response()
```

## The `response` helper

For explicit control, build a `Response`:

```python
from arvel import response

response({"ok": True}, status=201)                 # content + status
response.json(data, status=200)                    # JSON explicitly
response.no_content()                              # 204, empty body
response(content, status=200, headers={"X-App": "arvel"})
```

Attach or drop cookies fluently:

```python
response({"ok": True}).with_cookie("session", token, http_only=True, secure=True)
response(...).without_cookie("stale")
```

## Redirects

`redirect()` builds a redirect response (302 by default):

```python
from arvel import redirect

redirect("/dashboard")                             # to a path
redirect().route("users.show", id=7)               # to a named route (URL generated for you)
redirect().back(fallback="/")                      # to the previous URL, or the fallback
redirect().away("https://example.com")             # to an external URL
```

For the classic form-submit round trip, flash data onto the redirect — the next request's view
sees it (see [Session](session.md) and [Validation](validation.md)):

```python
redirect().back().with_input().with_errors(validator.errors())   # repopulate the form + show errors
redirect().route("posts.index").with_("status", "Post created")  # a one-request flash value
```

## File downloads & streaming

```python
response.download("invoices/2026-06.pdf")                 # Content-Disposition: attachment
response.download(path, name="report.pdf")                # override the download filename
response.file("images/logo.png")                          # inline (rendered in the browser)
response.stream(generator, headers={...})                 # stream a body chunk by chunk
```

## Status codes & headers

A route can also declare its success status at definition time (e.g. `201` for a create), and any
`Response` carries an explicit `status` and `headers` dict. For error responses, raising an HTTP
exception is usually cleaner than building the response by hand — see [Error Handling](errors.md).

## See also

- [Requests](routing.md) — reading input on the way in.
- [Views](views.md) — rendering HTML responses.
- [Routing](routing.md) — where handlers are registered and named.
