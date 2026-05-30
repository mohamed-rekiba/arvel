# URL Generation

Arvel provides the `Url` facade for generating URLs to named routes, signed URLs, and asset paths.

## Generating URLs to named routes

```python
from arvel.facades import Url

url = Url.route("users.show", user_id=42)
# → "/users/42"
```

Naming a route:

```python
@Route.get("/users/{user_id}", name="users.show")
async def show(user_id: int) -> dict[str, Any]: ...
```

## Absolute URLs

```python
url = Url.route("users.show", user_id=42, absolute=True)
# → "https://app.example.com/users/42"
```

The base URL comes from `APP_URL` in your `.env`.

## Signed URLs

For URLs that need to be tamper-proof — password resets, magic links, signed file downloads — use `Url.signed`:

```python
url = Url.signed("downloads.invoice", invoice_id=42, expires_in=timedelta(hours=1))
```

The URL embeds an HMAC signature and expiration timestamp. The route handler validates with the `SignedUrl` middleware:

```python
@Route.get("/downloads/invoices/{invoice_id}", name="downloads.invoice", middleware=[SignedUrl])
async def invoice(invoice_id: int) -> FileResponse: ...
```

## Current URL

```python
from arvel.facades import Request

Request.current_url()         # full URL including query string
Request.current_path()        # path portion
Request.full_url_with({"page": 2})  # current URL with merged query params
```

## In templates

Register `url` and `signed_url` as Jinja2 globals in your service provider:

```python
templates.env.globals["url"] = Url.route
templates.env.globals["signed_url"] = Url.signed
```

```jinja
<a href="{{ url('users.show', user_id=user.id) }}">View profile</a>
```

## See also

- [Routing](routing.md) — naming routes.
- [Requests](requests.md) — reading the current URL.
- [Encryption](encryption.md) — the HMAC implementation behind signed URLs.
