# Views

Of course, it's not practical to return entire HTML documents as strings directly from your routes and
controllers. Views provide a convenient way to place all of your HTML in separate files. arvel renders
views with **Jinja2**: a handler names a template, hands it some data, and gets back an HTML response.
(Building a JSON API or a SPA instead? Return models/resources from your handlers — see
[API Resources](database/resources.md) — and reach for views only for the HTML your app still serves.)

This page covers *returning* views and passing them data; the template **language** itself — control
structures, inheritance, components, and the available global functions — is covered in
[Templates](templates.md).

## Creating & rendering views

A view lives under `resources/views/` as a `.html` template. Render one with the `view()` helper,
which maps a **dotted name** to a file:

```python
from arvel import Route, view

async def home(request):
    return await view("pages.home", {"title": "Home"}).to_response()

Route.get("/", home, name="home")
```

`view(name, data)` maps `pages.home` → `resources/views/pages/home.html` and returns a `View`.
`view()` itself is synchronous (it builds the `View`); the render is async:

```python
await view("pages.home", data).to_response()   # → an HTML Response
await view("pages.home", data).render()        # → the raw rendered string
```

## Passing data to views

Pass a dict as the second argument; every key becomes a variable in the template:

```python
await view("pages.profile", {"user": user, "posts": posts}).to_response()
```

```html
<h1>{{ user.name }}</h1>
{% for post in posts %}<article>{{ post.title }}</article>{% endfor %}
```

## Sharing data with all views

Occasionally you need to share data with every view your app renders — a site name, the current
navigation. Register it once (typically from a service provider's `boot`) with `View.share`:

```python
app.make("view").share(app_name="Arvel", year=2026)
```

Shared values are available in every template alongside the built-in [global functions](templates.md#available-global-functions)
(`route`, `auth`, `asset`, `csrf_field`, …). For **per-request** shared data (flashed `errors` and
`old` input), the web group handles that for you — see [Validation](validation.md) and
[Session](session.md).

## Package views & namespaces

A package ships its own templates under a namespace, addressed as `namespace::template`:

```python
app.make("view").add_namespace("billing", "/path/to/billing/views")
await view("billing::invoice", {"total": total}).to_response()
```

## See also

- [Templates](templates.md) — the template language: inheritance, control structures, globals, forms.
- [Frontend](frontend.md) / [Asset Bundling](asset-bundling.md) — Vite assets and Inertia SPAs.
- [Routing](routing.md) — `Route.view(...)` renders a view with no controller.
- [Session](session.md) — flashed `errors` and `old()` input on a redirect-back.
