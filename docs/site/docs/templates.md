# Templates

Arvel uses **Jinja2** for HTML templates — the de-facto standard in the Python ecosystem. There is no Arvel-specific template language.

## Why Jinja2

- Mature, fast, widely understood
- Native FastAPI support via `Jinja2Templates`
- Strong editor support (syntax highlighting, autocomplete, IDE plugins)
- Familiar `{% ... %}` / `{{ ... }}` syntax

## Conventional patterns

### Layouts

```jinja
{# resources/views/layouts/base.html #}
<!DOCTYPE html>
<html lang="en">
  <head>
    <title>{% block title %}Arvel{% endblock %}</title>
  </head>
  <body>
    {% block content %}{% endblock %}
  </body>
</html>
```

### Extending a layout

```jinja
{# resources/views/users/show.html #}
{% extends "layouts/base.html" %}

{% block title %}{{ user.name }} — Arvel{% endblock %}

{% block content %}
  <h1>{{ user.name }}</h1>
  <p>{{ user.email }}</p>
{% endblock %}
```

### Including partials

```jinja
{% include "partials/nav.html" %}
```

### CSRF tokens in forms

```jinja
<form method="POST" action="{{ url('users.store') }}">
  {{ csrf_field() }}
  <input type="text" name="name">
</form>
```

Register `csrf_field` as a Jinja2 global in your service provider — see [CSRF Protection](csrf.md).

## See also

- [Views](views.md) — view file conventions.
- [URL Generation](urls.md) — the `url()` helper in templates.
- [CSRF Protection](csrf.md) — CSRF token rendering.
