# Asset Bundling

arvel doesn't own your JavaScript build — you bring the toolchain you like. What it provides is a thin,
production-ready bridge to [Vite](https://vitejs.dev): a manifest reader that turns your entry points
into the correct hashed `<script>` and `<link>` tags, so your templates never hard-code a built
filename.

> This page covers the server-side integration. For the broader picture — Vite vs. a full SPA via
> Inertia — see [Frontend](frontend.md).

## Introduction

In production, Vite writes a `manifest.json` mapping each source entry (`resources/js/app.js`) to its
hashed, cache-busted output file. arvel's `vite()` template helper reads that manifest and emits the
tags for you, including any CSS the entry imports.

## Loading assets in templates

Call `vite()` with one or more entry points in your layout's `<head>` — it's a registered template
global, so nothing needs to be passed from the controller:

```html
<!-- resources/views/layouts/app.html -->
<!doctype html>
<html>
  <head>
    {{ vite("resources/js/app.js") }}   <!-- <link> + module <script>, hashed -->
  </head>
  <body>{% block content %}{% endblock %}</body>
</html>
```

Pass several entries to bundle more than one:

```html
{{ vite("resources/css/app.css", "resources/js/app.js") }}
```

Each entry is resolved against the built manifest at `public/build/manifest.json`, served under the
`/build` base path.

### Resolving a single asset URL

When you need just the hashed URL of one built file (not the full tags), reach for the `Vite` class:

```python
from arvel.views.vite import Vite

url = await Vite().asset("resources/js/app.js")   # "/build/assets/app.6f3c1a.js"
```

Construct `Vite(manifest_path=..., base=...)` to point at a non-default manifest location or public
base path.

## Simple, unhashed assets

For static files that aren't part of the Vite build (a favicon, a logo), the `asset()` global joins a
path onto `config('app.asset_url')` (falling back to `app.url`) — no manifest lookup:

```html
<link rel="icon" href="{{ asset('favicon.ico') }}">
```

Use `vite()` for anything the bundler produces (so you get cache-busting) and `asset()` for static
public files.

## See also

- [Frontend](frontend.md) — choosing between bundled assets and an Inertia SPA.
- [Templates](templates.md) — the `vite()` / `asset()` globals in context.
- [Deployment](deployment.md) — building assets as part of your release.
