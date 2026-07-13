# URL Generation

arvel provides several helpers to generate URLs for your application — building links in templates,
redirecting to a named route, or producing a tamper-evident signed link for an email. They all read
`config('app.url')` for the host, so a URL generated in a background job matches one generated in a
request.

## The basics

### Generating URLs

The `url()` helper generates an absolute URL for any path:

```python
from arvel.routing import url

url("/pricing")          # "https://example.com/pricing"  (config('app.url') + path)
```

### Accessing the current URL

Called with no argument, `url()` returns the generator, which exposes request-scoped accessors:

```python
url().current()          # this request's absolute path, no query string
url().full()             # ...with the query string
url().previous("/")      # the Referer, or the fallback — never raises
url().query("/search", {"q": "books"})   # "/search?q=books"
```

`.current()`/`.full()` require an active request (they raise a `RuntimeError` outside one rather than
returning a nonsense path); `.previous()` always degrades to its `fallback`.

## URLs for named routes

Prefer generating URLs to **named** routes — the URL is derived from the route definition, so changing
a path updates every link automatically:

```python
from arvel.routing import route, to_route

route("users.show", user=7)                  # "https://example.com/users/7" — absolute by default
route("users.show", user=7, absolute=False)  # "/users/7" — the bare path
to_route("users.show", user=7)               # a Redirect — sugar for redirect().route(...)
```

Extra keyword arguments beyond the route's own parameters are appended as a query string.

## Signed URLs

Signed URLs carry a signature over the URL, so you can hand a link to an untrusted client (an
unsubscribe link in an email) and still detect tampering. An optional `expires` makes the link
temporary:

```python
from arvel.routing import temporary_signed_route

temporary_signed_route("unsubscribe", 3600, user=7)   # valid for the next hour
```

From a `Router` instance you also get the non-expiring form and manual verification:

```python
link = router.signed_url("unsubscribe", user=7)            # key defaults to the app key
router.has_valid_signature(signed_path)                    # integrity + not-expired
```

The signature is an itsdangerous MAC appended as a `signature` query param; the signing key defaults
to `config('app.key')` (pass `key=` to override — rotating the key invalidates old links).

### Validating signed route requests

Protect the receiving route with the **signed** middleware rather than checking by hand — a request
with a missing, tampered, or expired signature gets a **403** before the handler runs:

```python
from arvel.http.middleware import ValidateSignature

Route.get("/unsubscribe", unsubscribe, name="unsubscribe").middleware(ValidateSignature)
```

## URLs in templates

`route`, `url`, and `asset` are registered as template globals, so links need no controller plumbing:

```html
<a href="{{ route('users.show', user=user.id) }}">{{ user.name }}</a>
<link rel="stylesheet" href="{{ asset('css/app.css') }}">
```

## See also

- [Routing](routing.md) — defining and naming the routes these helpers target.
- [Responses](responses.md) — `redirect().route(...)` builds a redirect to a named route.
- [Templates](templates.md) — the `route`/`url`/`asset` globals in views.
