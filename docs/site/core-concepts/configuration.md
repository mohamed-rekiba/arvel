# Configuration

<a name="introduction"></a>
## Introduction

All of the configuration for an Arvel application is driven by environment variables and the config files in your project. Arvel offers two complementary ways to read configuration: a Laravel-style file registry accessed with `config("dotted.key")`, and typed `ArvelSettings` classes validated by Pydantic. This page covers both and when to reach for each.

<a name="quick-start"></a>
### Quick start

```python
# In application code — prefer config() or Config.of()
from arvel.config import config, Config
from arvel.config.db_config import DbConfig

app_name = config("app.name")
db = Config.of(DbConfig)
if db.enabled:
    dsn = db.async_url()
```

```bash
# Inspect at runtime
arvel config:show app.env
arvel config:show database.default

# Production — cache the file registry after deploy
arvel config:cache
```

| Need | Reach for |
|---|---|
| App-level toggles in `config/*.py` | `config("section.key")` |
| Validated subsystem config (DB, cache, queue) | `Config.of(SomeConfig)` |
| Raw env in a config file only | `env("KEY", default)` from `arvel.support.env` |

<a name="environment-configuration"></a>
## Environment Configuration

It is often helpful to have different configuration values based on the environment where the application is running. For example, you may wish to use a different cache driver locally than you do on your production server.

<a name="the-env-file"></a>
### The .env File

A fresh application ships with a `.env.example` you copy to `.env`. When the application is built, Arvel loads `.env` from the project root using python-dotenv. Crucially, it loads with `override=False`: any variable already present in the real process environment wins over the file. That makes container- and CI-provided env vars authoritative.

```ini
APP_NAME="My App"
APP_ENV=local
APP_DEBUG=true
APP_KEY=base64:...
APP_URL=http://localhost:8000

DB_CONNECTION=postgresql
DB_HOST=127.0.0.1
DB_DATABASE=myapp
```

> [!WARNING]
> Never commit your `.env` file to source control. It typically holds secrets — database passwords, the application key, API tokens. Commit `.env.example` (without real secrets) instead.

<a name="retrieving-environment-variables"></a>
### Retrieving Environment Variables

Read environment variables directly with the `env` helper. Pass a default to both supply a fallback and coerce the value to the default's type:

```python
from arvel.support.env import env

env("APP_NAME")                    # str | None
env("APP_NAME", "Arvel")           # str, defaulting to "Arvel"
env("APP_DEBUG", False)            # bool — "true"/"1"/"yes"/"on" → True
env("DB_PORT", 5432)               # int — coerced from the string
env("ALLOWED_HOSTS", [])           # list — CSV split on commas
env("API_KEY", required=True)      # str, or LookupError if unset
```

| Default type | Coercion |
|---|---|
| `bool` | `true`/`1`/`yes`/`on` → `True`; `false`/`0`/`no`/`off` → `False` (case-insensitive) |
| `int` / `float` | Parsed numerically; invalid input raises `EnvCoercionError` |
| `list` | Comma-separated string split into a list of stripped items |
| `str` / `None` | Returned as-is |

> [!NOTE]
> `env()` reads the raw process environment. Prefer reading configuration through `config()` or typed settings in application code, and reserve `env()` for inside config files — it keeps env access in one layer.

<a name="two-configuration-systems"></a>
## Two Configuration Systems

Arvel exposes configuration two ways. They use different runtime APIs, but they're connected: a typed settings class can pull its values straight from your `config/*.py` files (see [the cascade](#the-cascade)).

| System | API | Use it for |
|---|---|---|
| **File registry** | `config("app.name")` | App-level config you author in `config/*.py`, Laravel-style. |
| **Typed settings** | `Config.of(DbConfig)` | Validated, typed configuration sections (framework subsystems use these). |

<a name="config-files-and-config"></a>
## Config Files and config()

When you build the app with `with_config_dir(base_path / "config")`, Arvel loads every `config/*.py` module (non-recursive, skipping files prefixed with `_`). Each module's top-level variables become a config section named after the file:

```python
# config/app.py
from arvel.support.env import env

name: str = env("APP_NAME", "My App")
env: str = env("APP_ENV", "production").lower()
debug: bool = env("APP_DEBUG", False)
url: str = env("APP_URL", "http://localhost:8000")
is_production: bool = env == "production"
```

<a name="accessing-config-values"></a>
### Accessing Config Values

Read values with `config()`, using dot notation of `module_stem.attribute`. A missing key returns `None` (or a supplied default) rather than raising:

```python
from arvel.config import config

config("app.name")                 # "My App"
config("app.debug")                # True
config("database.default")         # "postgresql"
config("billing.plan", "free")     # default if the key is missing
```

Dict segments are looked up by key only. A missing key returns the default even when its name collides with a dict method — `config("cache.stores.get", "x")` returns `"x"`, never `dict.get`.

For a strict lookup that raises `ConfigKeyError` on a missing key, use `lookup()` instead of `config()`.

<a name="adding-your-own-config"></a>
### Adding Your Own Config

Add a new section by dropping a module into `config/`:

```python
# config/billing.py
from arvel.support.env import env

stripe_key: str = env("STRIPE_KEY", "")
trial_days: int = env("TRIAL_DAYS", 14)
```

```python
config("billing.stripe_key")
config("billing.trial_days")
```

<a name="typed-settings"></a>
## Typed Settings

For configuration you want validated and typed, define an `ArvelSettings` subclass — a Pydantic `BaseSettings` model. The framework's own subsystems (database, cache, sessions, queues, …) are configured this way.

<a name="defining-settings"></a>
### Defining Settings

Subclass `ArvelSettings`, declare typed fields with defaults, and register the class:

```python
from arvel.config import ArvelSettings, register


@register
class BillingConfig(ArvelSettings):
    stripe_key: str = ""
    trial_days: int = 14
```

Register at build time instead of (or in addition to) the `@register` decorator with `with_config_files`:

```python
Application.configure(base_path).with_config_files([BillingConfig]).create()
```

<a name="env-prefix-derivation"></a>
### Env Prefix Derivation

Each settings class derives an environment-variable prefix from its name: the trailing `Settings`/`Config` is stripped, the rest is upper-snake-cased, and a trailing underscore is added. So `BillingConfig` reads `BILLING_*` (e.g. `BILLING_STRIPE_KEY`), `DbConfig` reads `DB_*`, and `AppSettings` reads `APP_*`. Override the prefix by setting `model_config = SettingsConfigDict(env_prefix="CUSTOM_")` on the subclass. To read a bare, unprefixed variable, annotate the field with `NoPrefix`.

<a name="the-cascade"></a>
### Where Values Come From (the cascade)

A settings class resolves each field from the first source that has it:

```
explicit kwargs  >  config/*.py  >  environment variable  >  field default
```

The framework's built-in sections opt into their config file by pointing at a path in the file registry — `DbConfig` reads `database.connections.{default}`, `CacheConfig` reads `cache.stores.{default}`, `StorageConfig` reads `filesystems`, and so on. The `{default}` token uses the file's `default` to pick the active named entry (the same `connections`/`stores`/`disks` shape Laravel uses).

So the three cases you'd expect all hold, merged per field:

- A `config/*.py` that sets a key → that value wins.
- No config file (or the key is missing) → the env var, then the field default.
- A partial config file → its keys win; the rest fall to env, then default.

Config files stay self-describing because they keep their own `env("KEY", default)` calls — by the time a typed class reads them, the values are already env-resolved. A class that doesn't declare a config path just reads env → default as before.

<a name="reading-settings"></a>
### Reading Settings

Resolve a registered settings instance with `Config.of`:

```python
from arvel.config import Config

stripe_key = Config.of(BillingConfig).stripe_key
```

> [!NOTE]
> Registered settings are validated when the app boots (in `ConfigServiceProvider.boot`), not lazily on first access — so a misconfigured value fails fast at startup. Reading an unregistered class raises `ConfigNotRegisteredError`.

<a name="environments"></a>
## Environments

The current environment is exposed as `config("app.env")` and `app.environment()`. The framework keys a few safeguards off it: the database seeder and the destructive migration commands (`migrate:fresh`, `migrate:refresh`) refuse to run in production. (`key:rotate` carries the same production guard, but the command itself is still a stub — see [Encryption](../features/encryption.md#generating-and-rotating-keys).)

> [!NOTE]
> `APP_DEBUG` is present in the skeleton's `config/app.py` for parity, but it does not currently change the framework's error verbosity — unhandled errors never leak stack traces, in any environment. Control runtime detail through logging configuration (`LOG_LEVEL`, observability). See [Logging](../features/logging.md).

<a name="the-application-key"></a>
## The Application Key

Several features — [encryption](../features/encryption.md), encrypted casts, and [signed URLs](../the-basics/routing.md#signed-urls) — require an application key. It's read from `APP_KEY` and uses a `base64:`-prefixed value. Generate one with:

```bash
arvel key:generate
```

This writes (or replaces) the `APP_KEY` line in your `.env`. Use `--show` to print a key without writing it, and `--force` to overwrite a populated key.

<a name="configuration-caching"></a>
## Configuration Caching

To speed up booting, you can cache the `config/*.py` file registry into a single JSON file:

```bash
arvel config:cache      # write bootstrap/cache/config.json
arvel config:clear      # remove the cache and reset the in-memory registry
arvel config:show app.name   # print a single resolved value
```

The cache stores the `config/*.py` file registry. Typed `ArvelSettings` read that registry too (it's the top of [the cascade](#the-cascade)), so a cached config still drives them — just remember to re-run `config:cache` after changing a config file.

> [!WARNING]
> `config:cache` strips secret-named keys (`password`, `secret`, `token`, `credential`, `private`, and a bare `key`) before writing, so credentials never land in `bootstrap/cache/config.json`. Those keys fall back to the environment at load time. Keep secrets in discrete keys rather than embedded in connection strings — a URL like `postgres://user:pass@host` is not redacted.
