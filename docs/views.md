# Views

When you're rendering HTML on the server — a marketing page, an admin panel, an email-confirmation
screen — you want templates, not string concatenation. arvel renders views with **Jinja2**: a handler
names a template, hands it some data, and gets back an HTML response. (Building a JSON API or a
SPA instead? Return models/resources from your handlers — see [API Resources](database/resources.md) —
and reach for views only for the HTML your app still serves.)

The entry point is `view(name, data)`: it maps a dotted template name to a file and gives you back a
renderable `View`.

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

## Layouts & template inheritance

You rarely want every page to repeat the same `<head>`, navigation, and footer. Jinja2's template
inheritance lets you write that shell **once** as a layout and have each page fill in the parts that
differ. Define a base template with `{% block %}` holes:

```html
{# resources/views/layouts/app.html #}
<!doctype html>
<html>
  <head>
    <title>{% block title %}{{ config('app.name', 'arvel') }}{% endblock %}</title>
    <link rel="stylesheet" href="{{ asset('css/app.css') }}">
  </head>
  <body>
    <nav>{% if auth() %}Hi, {{ auth().name }}{% else %}<a href="{{ route('login') }}">Log in</a>{% endif %}</nav>
    <main>{% block content %}{% endblock %}</main>
  </body>
</html>
```

Then each page `extends` the layout and overrides only the blocks it cares about — template paths
inside `{% extends %}`/`{% include %}` are relative to `resources/views/`, the same root `view()`
resolves against:

```html
{# resources/views/pages/home.html #}
{% extends "layouts/app.html" %}

{% block title %}Home · {{ config('app.name') }}{% endblock %}

{% block content %}
  <h1>Welcome</h1>
  {% include "partials/feature-grid.html" %}   {# pull in a reusable fragment #}
{% endblock %}
```

The handler renders the page exactly as before — `await view("pages.home", {...}).to_response()` — and
Jinja assembles the layout, the page's blocks, and any included partials into one document. All the
[template globals](#template-globals) below are available inside the layout and every page that
extends it, so `route`, `auth`, and `asset` work everywhere without re-passing them.

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
| `auth()` · `guest()` | the current authenticated user (or `None`) / whether nobody is logged in |
| `csrf_token()` · `csrf_field()` | the session CSRF token / a hidden `_token` input |
| `method_field('PUT')` | a hidden `_method` input so a form can target a PUT/PATCH/DELETE route |

```html
<a href="{{ route('users.show', id=user.id) }}">{{ user.name }}</a>
<link rel="stylesheet" href="{{ asset('css/app.css') }}">

<form method="post" action="{{ url('/profile') }}">
  {{ csrf_field() }} {# required for web-group POSTs — see Routing/CSRF #}
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
request**: it's available on the request immediately after the redirect
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
(`password`, `password_confirmation`) are never flashed** — secrets stay out of the session.

## Sharing data with every view

Register globals once (e.g. from a service provider's `boot`) with `View.share`:

```python
app.make("view").share(app_name="Arvel", year=2026)
```

## Package views & namespaces

A package ships its own templates under a namespace, addressed as `namespace::template`:

```python
app.make("view").add_namespace("billing", "/path/to/billing/views")
await view("billing::invoice", {"total": total}).to_response()
```

## Common mistakes & gotchas

- **A POST that 419s.** Web-group forms need a CSRF token — drop `{{ csrf_field() }}` inside every
  `<form method="post">`. See [Middleware](middleware.md#csrf-from-a-spa-or-mobile-app).
- **Flash gone after a refresh.** `errors`, `old()`, and `flash(...)` live for **exactly one
  request** — they show once on the redirected-to page and then age out. Re-flash to keep them.
- **A form that can't PUT/DELETE.** HTML forms only speak GET/POST; add `{{ method_field('PUT') }}`
  to spoof the verb for a route bound to PUT/PATCH/DELETE.
- **Expecting `old()` to refill a password.** Password fields are never flashed — the user re-types
  them by design.
- **Awaiting the wrong thing.** `view(...)` is synchronous (it builds the `View`); the render is
  async — `await view(...).to_response()` (an HTML response) or `await view(...).render()` (the raw
  string).

## How it works

`view(name, data)` resolves the dotted name to a file under `resources/views/` (namespaced templates
resolve against their registered directory) and constructs a `View`. Rendering runs Jinja2 with the
template globals injected into the environment, so `route`/`auth`/`csrf_token`/`trans` resolve against
the running app at render time and degrade safely when there's no app or session. `to_response()`
wraps the rendered string in an HTML `Response`; the web middleware group is what shares the `errors`
bag and old input into the environment on a redirect-back.

## See also

- [Routing](routing.md) — `Route.view(...)` renders a view with no controller; CSRF protection.
- [Middleware](middleware.md#csrf-from-a-spa-or-mobile-app) — CSRF from a SPA or mobile app.
- [Localization](localization.md) — `trans`/`trans_choice` and publishable message files.
- [Validation](validation.md) — how the `errors` bag is populated.
