# Companion packages

Arvel keeps the core small. Optional features ship as separate packages you install as extras. Each one registers a service provider and, where it needs tables, publishes migrations under its own tag.

| Package | Extra | What it adds |
|---|---|---|
| [arvel-oauth](oauth.md) | `arvel[oauth]` | OAuth2/OIDC social login (Google, GitHub, Microsoft, Apple, generic OIDC) |
| [arvel-permission](permission.md) | `arvel[permission]` | Roles and permissions with mixins, middleware, and Gate integration |
| [arvel-image](image.md) | `arvel[image]` | Pillow-based image manipulation + a polymorphic media library |
| [arvel-search](search.md) | `arvel[search]` | Full-text search with pluggable drivers (database, Meilisearch, Elasticsearch) |
| [arvel-audit](audit.md) | `arvel[audit]` | Automatic change-audit trail + a fluent activity log |
| [arvel-ecommerce-demo](ecommerce-demo.md) | — | A full reference app you can read or scaffold |

## Installing and wiring a package

Install the extra:

```bash
uv add "arvel[image]"
```

Register its provider in `bootstrap/providers.py`:

```python
from arvel_image import ImageServiceProvider

providers = [
    # ...
    ImageServiceProvider,
]
```

If the package ships migrations, publish and run them:

```bash
arvel vendor:publish --tag=arvel-image
arvel migrate
```

See each package page for its specific configuration, models, and usage.
