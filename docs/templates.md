# Templates

Templates are arvel's server-side templating layer. Where [Views](views.md) cover *returning* a
template and passing it data, this page covers the template **language** itself — displaying data,
control structures, inheritance, and the form helpers. Templates are [Jinja](https://jinja.palletsprojects.com)
files under `resources/views/`, rendered asynchronously, with autoescaping on by default.

## Displaying data

Pass data to a view and echo it with `{{ }}`:

```python
return await view("greeting", {"name": "Ada"}).to_response()
```

```html
<h1>Hello, {{ name }}</h1>
```

Output is **HTML-escaped automatically**, so `{{ name }}` is safe against XSS. To render trusted HTML
verbatim, mark it `| safe` — only ever on values you control.

## Control structures

```html
{% if user.is_admin %}
  <a href="/admin">Dashboard</a>
{% elif user.is_member %}
  <span>Welcome back</span>
{% else %}
  <a href="/login">Sign in</a>
{% endif %}

<ul>
{% for post in posts %}
  <li>{{ loop.index }}. {{ post.title }}</li>
{% else %}
  <li>No posts yet.</li>
{% endfor %}
</ul>
```

## Template inheritance

Define a layout with named blocks, then extend it — the arvel equivalent of a master layout:

```html
{# resources/views/layouts/app.html #}
<!doctype html>
<html>
  <head><title>{% block title %}arvel{% endblock %}</title></head>
  <body>{% block content %}{% endblock %}</body>
</html>
```

```html
{# resources/views/posts/index.html #}
{% extends "layouts/app.html" %}
{% block title %}Posts{% endblock %}
{% block content %}
  {% for post in posts %}<article>{{ post.title }}</article>{% endfor %}
{% endblock %}
```

### Including subviews

```html
{% include "partials/_nav.html" %}
```

### Components (macros)

Reusable, parameterized fragments are expressed as macros:

```html
{% macro alert(message, kind="info") %}
  <div class="alert alert-{{ kind }}">{{ message }}</div>
{% endmacro %}

{{ alert("Saved!", kind="success") }}
```

## Forms & CSRF

State-changing forms must carry the CSRF token; `csrf_field()` emits the hidden input, and
`method_field()` spoofs `PUT`/`PATCH`/`DELETE` for HTML forms that only support `GET`/`POST`:

```html
<form method="POST" action="/posts/{{ post.id }}">
  {{ csrf_field() }}
  {{ method_field("PUT") }}
  <input name="title" value="{{ old('title', post.title) }}">
  {% if errors.title %}<span class="error">{{ errors.title[0] }}</span>{% endif %}
  <button>Save</button>
</form>
```

See [CSRF Protection](csrf.md) and [Validation](validation.md) for the mechanisms behind these helpers.

## Available global functions

These functions are registered on every template — no need to pass them from the controller:

| Function | Returns |
|----------|---------|
| `route(name, **params)` / `url(path)` | a URL to a named route / path |
| `asset(path)` | a URL to a bundled asset (see [Asset Bundling](asset-bundling.md)) |
| `vite(*entries)` | the hashed `<script>`/`<link>` tags for one or more Vite entries, as trusted `Markup` |
| `csrf_token()` / `csrf_field()` | the raw CSRF token / a hidden `_token` input |
| `method_field(method)` | a hidden `_method` input for verb spoofing |
| `trans(key, **repl)` / `trans_choice(key, n)` | a translated / pluralized string |
| `can(ability, *args)` / `cannot(...)` | authorization checks (see [Authorization](auth/authorization.md)) |
| `auth()` / `guest()` | the current user / whether the visitor is a guest |
| `config(key, default)` | a configuration value |
| `old(key, default)` / `errors` | repopulated input / the validation error map |

## See also

- [Views](views.md) — returning templates and passing them data.
- [Asset Bundling](asset-bundling.md) — the `asset()` helper and Vite integration.
- [Localization](localization.md) — `trans()` / `trans_choice()`.
