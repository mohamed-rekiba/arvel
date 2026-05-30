# Configuration

All Arvel configuration is **typed**. Every config object is a Pydantic `BaseSettings` subclass that the framework reads at boot time. There are no untyped `dict[str, Any]` config bags, no string keys to typo, and no `os.environ.get("...")` calls scattered through your code.

## Quick reference

| You want to… | Use |
|---|---|
| Define a typed config schema | Subclass `ArvelSettings` and decorate with `@register` |
| Read a value | `Config.of(MyConfig).field` |
| Override at runtime (tests) | `Config.fake(MyConfig(...))` |
| Inspect the env-var name | `MyConfig.model_config['env_prefix']` |

## Defining a config schema

```python
from pydantic import SecretStr
from arvel.config import ArvelSettings, register


@register
class DbConfig(ArvelSettings):
    url: str = "postgresql+asyncpg://localhost/app"
    password: SecretStr = SecretStr("")
    pool_size: int = 5
```

`ArvelSettings` is a thin wrapper around `pydantic_settings.BaseSettings`. The base class:

- Reads from environment variables.
- Reads from `.env` at the project root.
- Auto-derives an `env_prefix` from the class name (`DbConfig` → `DB_`).
- Treats nested fields as dunder-delimited (`DB_POOL_SIZE`).

`@register` makes the class available to `Config.of(...)`. Without it, `Config.of(DbConfig)` raises `ConfigNotRegistered`.

## Reading values

```python
from arvel.facades import Config

db = Config.of(DbConfig)
print(db.url)           # "postgresql+asyncpg://localhost/app" or whatever the env says
print(db.password)      # SecretStr — won't leak in repr/log
print(db.password.get_secret_value())  # the real value
```

`Config.of(...)` returns a **frozen** Pydantic model. Mutating it raises `pydantic.ValidationError`. That's deliberate — config should be a snapshot of boot-time state, not a global mutable bag.

## Environment-based configuration

Arvel resolves config values from these sources, with later sources overriding earlier:

1. The schema's `default=...` value.
2. The project's `.env` file (loaded once at boot).
3. The OS environment (`os.environ`).
4. Explicit overrides via `Config.fake(...)` (test-only).

### Your `.env` file

```env
APP_ENV=local
APP_DEBUG=true
DB_URL=postgresql+asyncpg://user:pass@127.0.0.1/myapp
DB_PASSWORD=changeme
CACHE_DRIVER=redis
QUEUE_DRIVER=redis
```

**Never commit `.env` to source control.** The starter `.gitignore` excludes it.

### Multi-environment patterns

For multiple environments, ship a `.env.example` (committed) and one `.env.<env>` per environment (gitignored):

```bash
ARVEL_ENV=production uv run uvicorn app:create_app --factory
```

`Application.configure(...).with_environment("production")` causes Arvel to load `.env.production` instead of `.env`.

## Faking config in tests

```python
from arvel.facades import Config
from myapp.config import DbConfig

def test_uses_test_db() -> None:
    Config.fake(DbConfig(url="sqlite+aiosqlite:///:memory:"))
    # ... rest of the test sees the fake
```

`Config.fake(...)` overrides the registered instance for the lifetime of the test. The default test fixture clears all fakes after each test.

## Configuration files

Arvel supports two styles of configuration. Most greenfield projects use only the first; legacy-port projects often use both.

### Typed config (`ArvelSettings`)

The preferred approach. Configuration lives in:

- **Code** — your `ArvelSettings` subclasses, type-checked and IDE-auto-completed.
- **Environment** — your `.env` and process environment.

If you prefer to keep config in YAML/TOML, write a small adapter that reads the file and overlays it onto the model — Pydantic Settings supports custom sources out of the box.

### File-based config (`config/*.py`)

For teams porting from Laravel or preferring a dict-style layout, Arvel also loads `config/*.py` files when you call `with_config_dir(path / "config")` on `ApplicationBuilder`. Each file's public module attributes become accessible via `lookup()`:

```python
# config/mail.py
DEFAULT = "smtp"
MAILERS = {
    "smtp": {"host": "smtp.mailpit.local", "port": 1025},
}
```

```python
from arvel.config import lookup

host = lookup("mail.MAILERS.smtp.host")   # "smtp.mailpit.local"
```

## Caching the config

For apps using `config/*.py` files, Arvel can serialize the loaded config to `bootstrap/cache/config.json` so subsequent boots skip the Python file import entirely:

```bash
arvel config:cache    # write bootstrap/cache/config.json
arvel config:clear    # delete the cache (next boot reads config/*.py again)
```

**When to run `config:cache`**: at the end of your deploy script, after config files are in their final state. The cache survives as long as `config/*.py` doesn't change — run `config:clear` or `config:cache` again after any config edit.

**What gets cached**: primitive-valued module attributes (strings, ints, bools, lists, dicts). Class objects, functions, and other non-serializable values are silently skipped — the framework still loads them at runtime from the Python files.

**`ApplicationBuilder` integration**: if `bootstrap/cache/config.json` exists under the app's base path, `ApplicationBuilder.with_config_dir(...)` uses it and skips the Python file import. If the file is missing or malformed, it falls back to loading `.py` files normally.

> **Typed config is unaffected**: `ArvelSettings` subclasses registered with `@register` always load from environment variables. The `config:cache` step only covers the `config/*.py` lookup registry.

### Bridging file-based config into typed services

Sometimes you want `config/*.py` dict values fed into a typed `ArvelSettings`-style service — for example, when a starter kit ships a familiar-shaped `config/mail.py` and you want to wire it into the `Mail` facade. Do the bridging in a service provider:

```python
from arvel.config import lookup
from arvel.contracts.support import ServiceProvider
from arvel.mail.config import MailerConfig
from arvel.mail.drivers import SmtpMailDriver
from arvel.facades import Mail


class MailServiceProvider(ServiceProvider):
    """Bridge between config/mail.py (Laravel-shaped) and the Mail facade."""

    def register(self) -> None:
        # Read the Laravel-shaped dict.
        cfg = lookup("mail")
        default_mailer = cfg["default"]
        mailer = cfg["mailers"][default_mailer]

        # Build the typed framework config.
        typed = MailerConfig(
            host=mailer["host"],
            port=mailer["port"],
            encryption=mailer.get("encryption"),
            username=mailer.get("username"),
            password=mailer.get("password"),
        )

        # Register a concrete driver against the typed config.
        Mail.register_driver(default_mailer, SmtpMailDriver(typed))

    def boot(self) -> None: ...
```

**Why a service provider, not direct construction**: the bridging happens once at boot, never on a request path. The provider runs after configuration is loaded and before any handler resolves the `Mail` facade — so the typed config is always available, and tests can override it with `Config.fake(MailerConfig(...))` without touching the Laravel-shaped dict.

**`arvel.config.lookup(key)`** reads dotted-path keys (`lookup("mail.mailers.smtp.host")`) from the merged `config/*.py` namespace. It's the only place untyped config touches your code; everything past the provider is fully typed.

When **not** to bridge: if you're starting greenfield, prefer the typed-only path (`@register class MailerConfig(ArvelSettings)`). The bridge is for compatibility, not preference.

## Debug mode

Toggle debug mode via `APP_DEBUG`:

```env
APP_DEBUG=true
```

When debug is on, Arvel renders detailed error pages with stack traces, prints query plans on slow queries, and adds verbose logging. **Never enable debug in production** — error pages may leak sensitive information.

## Maintenance mode

Put the app into maintenance mode with `arvel down` and bring it back with `arvel up`:

```bash
arvel down                        # return 503 to all requests
arvel down --secret <token>       # allow bypass via ?token=<token>
arvel down --retry 60             # set Retry-After header
arvel up                          # exit maintenance mode
```

See [Console — Maintenance mode](console.md#maintenance-mode) for the full reference.

## Where to next?

- [Directory Structure](structure.md) — how an Arvel app is laid out.
- [Service Providers](providers.md) — how config is wired into the container.
- [Deployment](deployment.md) — production environment-variable patterns.
