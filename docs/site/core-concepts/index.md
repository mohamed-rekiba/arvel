# Core Concepts

These pages explain how Arvel boots, wires dependencies, and exposes configuration. Read them once early — they make every other section easier.

## Recommended path

1. **[Request Lifecycle](lifecycle.md)** — `create_application()`, register vs boot, ASGI lifespan, shutdown.
2. **[Service Container](service-container.md)** — bindings, `make` / `amake`, `dep()`, scopes.
3. **[Service Providers](service-providers.md)** — where your app registers features; opt-in vs baseline providers.
4. **[Configuration](configuration.md)** — `config()` vs typed `ArvelSettings`, env cascade, caching.
5. **[Facades](facades.md)** — when to use `Cache.get(...)` vs constructor injection.

```text
bootstrap/app.py
    → Application.configure().create()     # sync register
    → into_asgi() / await app.boot()       # async boot
    → handlers resolve services via dep() or facades
```

## What's in this section

| Page | Covers |
|---|---|
| [Request Lifecycle](lifecycle.md) | Builder, `create()`, environment, serving, errors |
| [Service Container](service-container.md) | DI, binding lifetimes, contextual binding, tags |
| [Service Providers](service-providers.md) | `register` / `boot` / `shutdown`, CLI commands, publishing |
| [Configuration](configuration.md) | `.env`, `config/*.py`, `Config.of()`, `config:cache` |
| [Facades](facades.md) | Import paths, availability, testing with `fake()` |

## See also

- [CLI needs-based bootstrap](../cli/commands.md#needs-based-bootstrap) — how commands boot only the providers they need.
- [Testing](../features/testing.md) — boot a minimal app in tests with selected providers.
