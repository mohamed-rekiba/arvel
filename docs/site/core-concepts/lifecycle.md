# Request Lifecycle

<a name="introduction"></a>
## Introduction

When using any tool in the "real world", you feel more confident if you understand how that tool works. Application development is no different. When you understand how your framework functions, the tools feel less "magical" and you'll be more confident building your applications.

The goal of this page is to give you a good, high-level overview of how the Arvel framework boots and serves requests. The `Application` is the heart of it all — it owns the [service container](service-container.md), runs your [service providers](service-providers.md), and produces the ASGI application your server runs.

<a name="lifecycle-overview"></a>
## Lifecycle Overview

<a name="first-steps"></a>
### First Steps

The entry point for an Arvel application is `public/asgi.py`. It calls `create_application()` from `bootstrap/app.py` and turns the result into an ASGI app:

```python
# public/asgi.py
from bootstrap.app import create_application

asgi = create_application().into_asgi()
```

`create_application()` assembles the `Application` from its parts. You serve `public.asgi:asgi` with an ASGI server like uvicorn.

<a name="building-the-application"></a>
### Building the Application

You rarely instantiate `Application` directly. Instead, `bootstrap/app.py` builds it through `Application.configure(...)`, which returns an `ApplicationBuilder` you chain to declare config, providers, and routes:

```python
from pathlib import Path
from arvel import Application

_BASE_PATH = Path(__file__).resolve().parent.parent


def create_application() -> Application:
    routes_dir = _BASE_PATH / "routes"
    return (
        Application.configure(_BASE_PATH)
        .with_config_dir(_BASE_PATH / "config")
        .with_providers(_BASE_PATH / "bootstrap" / "providers.py")
        .with_routing(
            web=routes_dir / "web.py",
            api=routes_dir / "api.py",
            console=routes_dir / "console.py",
        )
        .create()
    )
```

<a name="the-register-and-boot-phases"></a>
### The Register and Boot Phases

Service providers boot the framework in two distinct phases. Understanding the difference between them is the key to wiring services correctly:

- **register** is synchronous and runs during `create()`. Providers bind things into the [container](service-container.md) here — nothing more. Don't do I/O or resolve another provider's services; they may not be bound yet.
- **boot** is asynchronous and runs after *every* provider has registered. By the time `boot()` runs, every binding exists, so it's safe to resolve and wire services together, attach listeners, open connections, and so on.

```python
await app.boot()
```

`boot()` runs explicitly like this (common in scripts and tests) or automatically through the ASGI lifespan when the app is served.

<a name="producing-the-asgi-application"></a>
### Producing the ASGI Application

Once built and booted, the application becomes an ASGI app via `into_asgi()`:

```python
asgi = app.into_asgi()
```

`into_asgi()` returns a FastAPI application with the [exception handler](../the-basics/error-handling.md) registered, your [routes](../the-basics/routing.md) mounted, a health route added, and the middleware stack installed. The request scope middleware is always present; observability, context, deferred-task, and maintenance middleware are added when enabled.

<a name="the-application-builder"></a>
## The Application Builder

`Application.configure(base_path)` returns an `ApplicationBuilder`. Each builder method returns the builder, so calls chain.

<a name="builder-methods"></a>
### Builder Methods

| Method | Purpose |
|---|---|
| `with_providers(list \| Path)` | Your [service providers](service-providers.md), as a class list or a path to a module that exposes a `providers` list. |
| `with_environment(name)` | Force the environment (`"production"`, `"testing"`, …). |
| `with_config_dir(path)` | A directory of `config/*.py` modules, enabling dotted-key [`config()`](configuration.md) lookups. |
| `with_config_files([...])` | Register typed [`ArvelSettings`](configuration.md) classes explicitly. |
| `with_routing(web=, api=, console=)` | Route module paths to load. At least one is required. |
| `create()` | Build and return the `Application`. |

> [!NOTE]
> There is no `with_settings` or `with_middleware` on the builder. Settings come from `with_config_dir` / `with_config_files`, and middleware is attached to [routes and groups](../the-basics/middleware.md) or added to the ASGI app.

<a name="what-create-does"></a>
### What create() Does

`create()` runs a fixed sequence:

1. Load `.env` from `base_path/.env` via python-dotenv, with `override=False` — variables already in the process environment win.
2. Load the config directory (or a config cache, if one exists) when `with_config_dir` was used.
3. Load the providers module when `with_providers` was given a path.
4. Load the `web` and `api` route modules, executing their decorators.
5. Construct the `Application`, resolve the full provider chain (framework baseline + yours), and run every provider's synchronous `register()`.

> [!WARNING]
> `with_routing(console=...)` records the path, but the console route module is **not** loaded during `create()` yet. Define scheduled tasks and console commands as classes for now — see [Task Scheduling](../features/scheduling.md) and the [CLI reference](../cli/commands.md).

> [!NOTE]
> After `create()`, container bindings from `register()` are available, but the asynchronous `boot()` has not run. Call `await app.boot()` (scripts/tests) or let the ASGI lifespan do it (serving).

<a name="environment-resolution"></a>
## Environment Resolution

The application environment is resolved in this order:

1. An explicit `with_environment(...)` value.
2. `config("app.env")`, if a config directory is loaded.
3. The `APP_ENV` environment variable, lowercased (defaulting to `"production"`).

Read it at runtime with `app.environment()`. A handful of framework safeguards key off the environment — for instance, destructive migration commands and the database seeder refuse to run when the app is in production. See [Configuration](configuration.md#environments).

<a name="serving-the-application"></a>
## Serving the Application

In development you typically serve the module-level ASGI app with uvicorn, or use the `arvel serve` command, which runs `public.asgi:asgi`:

```bash
arvel serve
arvel serve --host 0.0.0.0 --port 8080 --reload
```

To run programmatically without the uvicorn CLI, use the `serve` helper, which boots through the ASGI lifespan:

```python
from arvel import serve

serve(app, host="127.0.0.1", port=8000)
```

<a name="shutdown"></a>
## Shutdown

On shutdown, the application disconnects registered services and runs each provider's `shutdown()` in **reverse** registration order:

```python
await app.shutdown()
```

Under ASGI this fires automatically on lifespan shutdown.

Teardown is best-effort: every provider's `shutdown()` runs even if an earlier one raises, so a single failing provider can't strand the others (the database provider still disposes its connection pool, for example). The first failure is re-raised as `ShutdownError` once all providers have run, and the app is always left un-booted.

<a name="lifecycle-errors"></a>
## Lifecycle Errors

| Exception | Raised when |
|---|---|
| `BootError` | A provider's `register()` or `boot()` raises. |
| `ShutdownError` | A provider's `shutdown()` raises — surfaced for the first failure after every provider has torn down. |
| `EnvironmentNotSetError` | `environment()` or `base_path()` is called before the app is configured. |
