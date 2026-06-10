# Companion packages

Arvel keeps the core small. Optional features ship as separate packages you install as extras. Each one registers a service provider and, where it needs tables, publishes migrations under its own tag.

| Package | Extra | What it adds | Migrations |
|---|---|---|---|
| [arvel-oauth](oauth.md) | `arvel[oauth]` | OAuth2/OIDC social login (Google, GitHub, Microsoft, Apple, generic OIDC) | `oauth_accounts` |
| [arvel-permission](permission.md) | `arvel[permission]` | Roles and permissions with mixins, middleware, and Gate integration | 5 pivot tables |
| [arvel-image](image.md) | `arvel[image]` | Pillow-based image manipulation + a polymorphic media library | `media` |
| [arvel-search](search.md) | `arvel[search]` | Full-text search with pluggable drivers (database, Meilisearch, Elasticsearch) | none |
| [arvel-audit](audit.md) | `arvel[audit]` | Automatic change-audit trail + a fluent activity log | `audit_entries`, `activity_entries` |

Looking for a full reference app? See the [e-commerce kit](../kits/ecommerce-kit.md) — it wires permission, image, and audit together in a real app.

<a name="quick-start"></a>
## Quick Start

Every package follows the same three steps:

```bash
# 1. Install the extra
uv add "arvel[permission]"
```

```python
# 2. Register the provider in bootstrap/providers.py
from arvel_permission import PermissionServiceProvider

providers = [
    # ...
    PermissionServiceProvider,
]
```

```bash
# 3. Publish migrations (when the package has them) and migrate
arvel vendor:publish --tag=arvel-permission
arvel migrate
```

Then follow the package page for model mixins, configuration, and usage. Packages without migrations (`arvel-search`) skip step 3.

<a name="choosing-a-package"></a>
## Choosing a Package

| You need… | Reach for… |
|---|---|
| "Sign in with Google/GitHub" | [arvel-oauth](oauth.md) |
| Role-based access, route guards, `Gate` checks | [arvel-permission](permission.md) |
| Product images, avatars, file uploads with conversions | [arvel-image](image.md) |
| Admin search, typeahead, Scout-style indexing | [arvel-search](search.md) |
| Compliance trail, "who changed what when" | [arvel-audit](audit.md) |
| Business events ("Order exported", "User invited") | [arvel-audit](audit.md) activity log |

Packages compose freely — the e-commerce kit uses permission + image + audit on the same models without conflict.

<a name="installing-and-wiring"></a>
## Installing and Wiring a Package

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

Some packages also ship install shortcuts that publish migrations in one step:

```bash
arvel oauth:install    # arvel-oauth
arvel audit:install    # arvel-audit
```

See each package page for its specific configuration, models, and usage.

<a name="common-requirements"></a>
## Common Requirements

Several packages depend on core infrastructure that's already wired in a typical Arvel app:

| Requirement | Used by |
|---|---|
| `DatabaseServiceProvider` + active session | permission, oauth, image, audit |
| `APP_KEY` set (`arvel key:generate`) | oauth (token encryption), audit (optional value encryption) |
| Queue worker running | search (`SEARCH_QUEUE_SYNC=true`), image (queued conversions) |
| Auth middleware setting `request.state.user` | permission middleware |

If a package method raises `RuntimeError` about a missing session, confirm `DatabaseServiceProvider` is registered and the call runs inside a request or an explicit `DB.transaction()` block.
