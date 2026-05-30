# Package Development

You can extend Arvel with packages — distributable Python libraries that ship routes, models, migrations, providers, and config. Arvel doesn't require a special skeleton; a normal `pyproject.toml` package works.

## Recommended layout

```
my-package/
├── pyproject.toml
├── src/
│   └── my_package/
│       ├── __init__.py
│       ├── provider.py          # MyPackageServiceProvider
│       ├── routes.py
│       ├── models.py
│       └── migrations/
│           └── 2026_01_01_000000_create_widgets.py
└── tests/
```

## Shipping a service provider

```python
# src/my_package/provider.py
from arvel.providers import ServiceProvider
from arvel.facades import Route

from .routes import register_routes


class MyPackageServiceProvider(ServiceProvider):
    def register(self) -> None:
        self.app.config.merge_from(_default_config(), prefix="my_package")
        self.app.bind(MyPackageClient, _build_client)

    def boot(self) -> None:
        register_routes()
        self.app.add_migration_path("my_package.migrations")
```

## Auto-discovery

Packages can opt into auto-discovery by declaring the provider in `pyproject.toml`:

```toml
[project.entry-points."arvel.providers"]
my_package = "my_package.provider:MyPackageServiceProvider"
```

Arvel reads the entry point during boot and registers the provider automatically.

## Shipping migrations

Place migration files under `<package>/migrations/` and call `self.app.add_migration_path(...)` in `boot()`. `arvel migrate` will pick them up alongside the application's own migrations.

## Publishing config

Ship a default config dict in `register()` and document the env-var overrides in the package README. Users override via `.env`:

```env
MY_PACKAGE_API_KEY=...
```

## See also

- [Service Providers](providers.md) — the provider lifecycle.
- [Configuration](configuration.md) — config merging rules.
