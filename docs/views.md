# Views

Server-rendered HTML with **Jinja2**. A handler builds a view from a dotted template name and turns
it into an HTML response — Laravel's `view('pages.home', [...])`.

## Rendering a view

```python
from arvel import Route, view

async def home(request):
    return await view("pages.home", {"title": "Home"}).to_response()

Route.get("/", home, name="home")
```

`view(name, data)` maps the **dotted name** to a template file under `resources/views/`
(`pages.home` → `resources/views/pages/home.html`). It returns a `View`; `await …​.to_response()`
renders it (async) to an HTML response, or `await …​.render()` for the raw string.

## Template globals

These helpers are available in every template with no imports — they resolve against the running
app and degrade safely when there's no app/session:

| Global | What it does |
|--------|--------------|
| `route('users.show', id=1)` | URL for a named route |
| `url('/login')` | join `config('app.url')` with a path |
| `asset('css/app.css')` | asset URL (`config('app.asset_url')` ‖ `app.url`) |
| `config('app.name', 'arvel')` | read a config value |
| `trans('messages.saved')` · `trans_choice('items', n)` | translations (see [Localization](localization.md)) |
| `can('update', post)` · `cannot('delete', post)` | authorization gate checks |
| `csrf_token()` · `csrf_field()` | the session CSRF token / a hidden `_token` input |

```html
<a href="{{ route('users.show', id=user.id) }}">{{ user.name }}</a>
<link rel="stylesheet" href="{{ asset('css/app.css') }}">

<form method="post" action="{{ url('/profile') }}">
  {{ csrf_field() }}            {# required for web-group POSTs — see Routing/CSRF #}
  {% if can('update', user) %}<button>Save</button>{% endif %}
</form>
```

## Validation errors

In the web group the `errors` bag is shared into every template (flashed on a failed validation
redirect), so forms can show messages after a redirect-back:

```html
{% if errors %}<ul>{% for field, msgs in errors.items() %}<li>{{ msgs[0] }}</li>{% endfor %}</ul>{% endif %}
```

Flashed data — the `errors` bag and any `flash("status", …)` message — lives for **exactly one
request** (Laravel's flash lifecycle): it's available on the request immediately after the redirect
and then aged out, so a refresh of the destination page no longer shows it. Re-flash within a request
to keep it for another hop.

### Repopulating forms — `old()`

When `request.validate(...)` fails on the web group, the submitted input is flashed too, so the
redirected-back form can refill the fields the user already typed. Read it in a template with the
`old()` global — `old("field", default)`:

```html
<input name="email" value="{{ old('email', '') }}">
{% if errors.email %}<span class="error">{{ errors.email[0] }}</span>{% endif %}
```

Like the rest of the flash, old input lives for exactly one request. **Password fields
(`password`, `password_confirmation`) are never flashed** — secrets stay out of the session
(Laravel's `dontFlash`).

## Sharing data with every view

Register globals once (e.g. from a service provider's `boot`) — Laravel's `View::share`:

```python
app.make("view").share(app_name="Arvel", year=2026)
```

## Package views & namespaces

A package ships its own templates under a namespace, addressed as `namespace::template`:

```python
app.make("view").add_namespace("billing", "/path/to/billing/views")
await view("billing::invoice", {"total": total}).to_response()
```

## See also

- [Routing](routing.md) — `Route.view(...)` renders a view with no controller; CSRF protection.
- [Middleware](middleware.md#csrf-from-a-spa-or-mobile-app) — CSRF from a SPA or mobile app.
- [Localization](localization.md) — `trans`/`trans_choice` and publishable message files.
- [Validation](validation.md) — how the `errors` bag is populated.
