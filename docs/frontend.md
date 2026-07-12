# Frontend

arvel is backend-first: it owns your server templates, the [Vite](https://vitejs.dev) asset
manifest, and the Inertia protocol — but it doesn't own your JavaScript build. You bring the JS
toolchain you like; arvel bridges it to the server.

There are two common approaches: server-rendered HTML with a sprinkle of bundled assets, or a
single-page app driven by Inertia.

## Bundled assets (Vite)

Run Vite as your asset pipeline. In production it writes a `manifest.json`; arvel's `vite()`
template helper reads it and emits the correct hashed `<script>`/`<link>` tags for your entry
points:

```html
<!-- resources/views/layouts/app.html -->
<!doctype html>
<html>
  <head>{{ vite("resources/js/app.js") }}</head>
  <body>{% block content %}{% endblock %}</body>
</html>
```

`vite(*entries)` resolves each entry against the built manifest, including any CSS the entry
imports. In development, point it at your Vite dev server; in production it serves the hashed,
cache-busted files Vite emitted. See [Views](views.md) for the templating side.

## Single-page apps (Inertia)

For a SPA without building an API, arvel speaks the [Inertia](https://inertiajs.com) protocol.
Return `inertia(component, props)` from a handler — arvel answers a JSON page object to an
`X-Inertia` request and the full HTML shell to a normal browser navigation:

```python
from arvel.views import inertia

async def dashboard(request):
    return await inertia("Dashboard", {"user": request.user().to_dict()})
```

The protocol details are handled for you:

- **Asset versioning** — each response carries the current asset version; a GET whose client
  version is stale gets a `409` with `X-Inertia-Location`, so the browser does a full reload onto
  the new bundle instead of swapping props into an old one.
- **Partial reloads** — an `X-Inertia-Partial-Data` request receives only the requested props.

The `--profile inertia-vue` scaffold (`arvel new app --profile inertia-vue`) wires a Vue + Inertia
+ Vite starting point.

## Which one?

- Mostly server-rendered pages, a little interactivity → **Vite** + [templates](views.md).
- App-like UI, client-side routing, but you'd rather not hand-roll an API → **Inertia**.
- A fully separate frontend hitting your JSON API → skip both; build your `/api` routes
  ([Routing](routing.md)) and consume them however you like.
