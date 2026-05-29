# Service Providers

Service providers are the central place to configure your application. They're where you bind classes into the [Service Container](container.md), register event listeners, register middleware, and load routes.

If you've used Laravel, the concept is identical. Every Arvel application — including the framework itself — boots through a chain of service providers.

## Writing a provider

A provider is any class that inherits from `arvel.ServiceProvider`:

```python
from arvel import Application, ServiceProvider


class AppProvider(ServiceProvider):
    def register(self) -> None:
        """Synchronously bind things into the container."""
        self.app.container.singleton(Clock, SystemClock)
        self.app.container.bind(Mailer, lambda c: SmtpMailer(c.resolve(Config)))

    async def boot(self) -> None:
        """Asynchronously wire side effects after every provider has registered."""
        await self.app.container.make(MigrationRunner).run()
        Event.listen("user.registered", SendWelcomeEmail)
```

Register it on your `Application`:

```python
app = (
    Application.configure(".")
    .with_environment("local")
    .with_providers([AppProvider])
    .create()
)
```

## `register()` vs `boot()`

This split is the most important concept.

| Method | Phase | Allowed to | Forbidden from |
|---|---|---|---|
| `register()` | Synchronous, during `into_asgi()` | Bind classes, factories, singletons, instances | Resolving services from other providers, doing I/O, awaiting anything |
| `boot()` | Async, during ASGI lifespan startup | Resolving services, doing I/O, awaiting | (no restrictions) |

The rule: **every `register()` runs before any `boot()`**. That ordering guarantees a provider's `boot()` can safely depend on bindings from any other provider — because all of them are already registered.

### Why not just one method?

Because cross-provider dependencies need a deterministic resolution order. Without the split, provider A's `register` would resolve provider B's binding, which might not yet exist. By forcing all `register` calls first, we eliminate the ordering problem.

## Common patterns

### Binding a singleton from config

```python
def register(self) -> None:
    self.app.container.singleton(
        RedisClient,
        lambda c: RedisClient.from_url(c.resolve(RedisConfig).url),
    )
```

### Registering an event listener

```python
async def boot(self) -> None:
    Event.listen(OrderShipped, NotifyCustomer)
```

### Registering a route group

If your provider owns a lot of routes, register them in `boot()`:

```python
async def boot(self) -> None:
    with Route.group(prefix="/api/v1", middleware=[Throttle(60)]):
        @Route.get("/me")
        async def me(): ...
```

### Tagged providers (deferred boot)

If a provider only needs to boot when a certain feature is used, mark it deferred:

```python
class TelescopeProvider(ServiceProvider):
    deferred = True
    provides = [TelescopeRecorder]
```

The container resolves `TelescopeRecorder` lazily, calling `boot()` only at first use.

## Framework-provided providers

These ship with Arvel and are registered by default for most starter apps:

| Provider | Provides |
|---|---|
| `ConfigServiceProvider` | Reads `.env` and `ArvelSettings` subclasses |
| `HttpServiceProvider` | Mounts routes, wires middleware pipeline |
| `DatabaseServiceProvider` | Engine, session maker, request-scoped session, `Schema` |
| `CacheServiceProvider` | `Cache` facade backed by the configured driver |
| `SessionServiceProvider` | Session store + cookie middleware |
| `QueueServiceProvider` | `Bus` facade, worker registry |
| `MailServiceProvider` | `Mail` facade |
| `NotificationServiceProvider` | `Notification` channels |
| `EventServiceProvider` | `Event` facade + listener registry |
| `AuthServiceProvider` | Full auth layer — guards, HTTP endpoints, middleware, publish tags, `auth:install` command |

You don't have to register them manually if you use `Application.configure(...).create()` without overriding providers — the framework includes them by default.

## AuthServiceProvider in detail

`AuthServiceProvider` is the largest opt-in provider — it wires the entire authentication layer from a single registration.

### What it registers

**In `register()` (synchronous):**

| Binding | Class |
|---|---|
| `AuthManager` | Multi-guard manager, powers `Auth::user()` |
| `AuthService` / `AuthBroker` | Login, register, token issuance, refresh rotation |
| `PasswordService` | Forgot-password / reset-password flow |
| `EmailVerificationService` | Signed URL generation and verification |
| `AuthController` | The 9 built-in HTTP endpoints |

It also mounts routes immediately in `register()` (not `boot()`) because FastAPI's router must be populated before `create_asgi()` finalises the route table.

**In `boot()` (async):**

- Registers the default event listeners: `Registered → SendVerificationEmail`, `PasswordResetRequested → SendPasswordResetEmail` (skipped if your app already registered its own listeners for those events).
- Wires `EmailVerificationService` into the listener module.
- Declares four publish tag groups (see below).

### Publish tags

`AuthServiceProvider` uses `self.publishes(...)` to declare files that can be copied into your project with `arvel vendor:publish --tag <tag>`. The `auth:install` command runs all four at once.

| Tag | Files published |
|---|---|
| `arvel-auth-config` | `config/auth.py` |
| `arvel-auth-migrations` | `database/migrations/*_create_users_table.py`, `*_create_refresh_tokens_table.py`, `*_create_personal_access_tokens_table.py`, `*_create_password_reset_tokens_table.py` |
| `arvel-auth-views` | `templates/auth/emails/verify_email.{html,txt}.j2`, `templates/auth/emails/password_reset.{html,txt}.j2`, `templates/layouts/base.html.j2` |
| `arvel-auth-routes` | `routes/auth.py` |

Publish individual tags when you only need part of the defaults:

```bash
# Only the config file
uv run arvel vendor:publish --tag arvel-auth-config

# Only the email templates (to customise them)
uv run arvel vendor:publish --tag arvel-auth-views
```

### Customising without forking

`AuthServiceProvider` is designed to be subclassed. Override only the piece you need:

```python
from arvel.auth import AuthServiceProvider
from arvel.auth.middleware.throttle_login import ThrottleLoginMiddleware
from arvel.mail.mailable import Mailable


class MyAuthProvider(AuthServiceProvider):
    # Change the rate-limit window
    def make_throttle_middleware(self) -> ThrottleLoginMiddleware:
        return ThrottleLoginMiddleware(max_attempts=10, window_seconds=120)

    # Swap the verification email for your own branded template
    def make_verify_email_mailable_class(self) -> type[Mailable]:
        return MyVerifyEmailMailable

    # Swap the password-reset email
    def make_password_reset_mailable_class(self) -> type[Mailable]:
        return MyPasswordResetMailable
```

Register your subclass instead of the base:

```python
app = (
    Application.configure(".")
    .with_providers([MyAuthProvider()])
    .create()
)
```

## Publishing provider assets

Any provider can declare publishable files with `self.publishes(...)`:

```python
class MyPackageProvider(ServiceProvider):
    async def boot(self) -> None:
        from pathlib import Path

        stub_dir = Path(__file__).parent / "stubs"
        self.publishes(
            {
                stub_dir / "config.py": "config/my-package.py",
                stub_dir / "migration.py": "database/migrations",
            },
            tag="my-package",
        )
```

Users install it with:

```bash
uv run arvel vendor:publish --tag my-package
```

Pass `is_migrations=True` for migration files — Arvel will prepend a timestamp to the filename automatically.

## Where to next?

- [Service Container](container.md) — what providers register into.
- [Facades](facades.md) — how facade access becomes a container resolve.
- [Configuration](configuration.md) — what providers read at boot.
