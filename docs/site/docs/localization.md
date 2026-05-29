# Localization

Arvel ships a full i18n layer: a `Translator`, JSON and Python file loaders, a `SetLocaleMiddleware` that negotiates the locale per request, a request-aware `t()` helper for controllers, and an HTTP catalog endpoint for serving translations to SPAs.

## Configuration

```python
# config/app.py
class AppSettings(ArvelSettings):
    locale: str = "en"
    fallback_locale: str = "en"
    available_locales: list[str] = ["en", "es", "fr"]
```

## Translation files

Arvel supports two file formats. JSON is recommended for most apps because it's easy to export to a SPA.

### JSON

```
resources/lang/
└── en/
│   └── messages.json
└── es/
    └── messages.json
```

```json
// resources/lang/en/messages.json
{
  "greeting": "Hello :name",
  "invoices.unpaid": "You have :count unpaid invoice(s)."
}
```

```json
// resources/lang/es/messages.json
{
  "greeting": "Hola :name",
  "invoices.unpaid": "Tienes :count factura(s) impagada(s)."
}
```

Wire up the loader in a service provider:

```python
from arvel.i18n import JsonFileLoader, Translator
from pathlib import Path


translator = Translator(
    loader=JsonFileLoader(Path(".")),
    default_locale="en",
    fallback_locale="en",
)
```

### Python files

```python
# resources/lang/en/messages.py
TRANSLATIONS = {
    "greeting": "Hello :name",
}
```

Use `PythonFileLoader` instead of `JsonFileLoader`. Python files let translation values be type-checked at the cost of SPA-friendliness.

## Per-request locale with `SetLocaleMiddleware`

`SetLocaleMiddleware` negotiates the locale on every request in this order:

1. `request.state.locale` — set by a user-preference guard upstream
2. `Accept-Language` header — picks the highest-quality supported locale
3. The configured default

```python
from arvel.i18n.middleware import SetLocaleMiddleware


with Route.group(middleware=[
    SetLocaleMiddleware(supported=["en", "es", "fr"], default="en")
]):
    @Route.get("/dashboard")
    async def dashboard(): ...
```

Or apply it globally in your HTTP service provider:

```python
class HttpServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        Route.use([SetLocaleMiddleware(supported=["en", "es", "fr"])])
```

## The `t()` helper

Inside a controller or route handler, use the request-aware `t()` helper. It reads the locale already negotiated by `SetLocaleMiddleware`:

```python
from arvel.i18n import t


async def dashboard(request: Request) -> JSONResponse:
    return JSONResponse({"message": t(request, "messages.greeting", name="Alice")})
```

`t()` performs `:placeholder` substitution and falls back to the configured `fallback_locale` when the locale is absent from the request state.

## i18n catalog API

For SPAs that need to fetch translations at runtime, mount `CatalogController`:

```python
from arvel.i18n.catalog import CatalogController
from pathlib import Path


ctrl = CatalogController(locales_dir=Path("resources/lang"))

Route.get("/api/i18n/{locale}", ctrl.serve)
```

`GET /api/i18n/en` returns:

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "a1b2c3d4e5f6a7b8"
Cache-Control: public, max-age=3600

{"greeting": "Hello :name", ...}
```

Subsequent requests that include `If-None-Match` with the ETag get a `304 Not Modified`, saving bandwidth. Locales are validated against the BCP 47 format (`en`, `en-GB`, `zh-Hant-HK`); unknown or malformed locales return `404`.

## Injecting a user's preferred locale

Set `request.state.locale` upstream of `SetLocaleMiddleware` to override `Accept-Language`:

```python
class UserLocaleMiddleware:
    async def handle(self, request, call_next):
        user = request.state.user  # assumes auth has run first
        if user and user.locale:
            request.state.locale = user.locale
        return await call_next(request)
```

`SetLocaleMiddleware` checks `request.state.locale` before inspecting headers, so any value you set there wins.

## In Jinja templates

```python
from arvel.i18n import t

templates.env.globals["t"] = lambda key, **kw: t(request, key, **kw)
```

```jinja
<h1>{{ t('messages.greeting', name=user.name) }}</h1>
```

## See also

- [Middleware](middleware.md) — `SetLocaleMiddleware` in the built-in table.
- [Configuration](configuration.md) — locale settings.
