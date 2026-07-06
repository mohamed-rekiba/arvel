# Configuration

Every arvel app needs values that change between environments — the app name, debug flag, database
URL, cache driver, secret keys. arvel keeps these in a single **configuration repository**: a
dotted-key store you read with the `config()` helper. Environment-specific secrets come from the
environment (and `.env` files); everything else is plain config data.

## Reading configuration

`config()` is the front door. Call it with a **dotted key** to read a value, with a key and a default
for a fallback, or with no argument to get the repository itself:

```python
from arvel import config

config("app.name")                 # "arvel"
config("app.timezone", "UTC")      # the value, or "UTC" if unset
config()                           # the Repository instance
```

Keys are dotted paths into a nested dict — `config("database.connections.pg.host")` walks
`database → connections → pg → host`. A miss at any level returns the default (`None` if you didn't
pass one); it never raises for an absent key.

```python
config("nope.not.here")            # None
config("nope.not.here", "x")       # "x"
```

### Writing at runtime

You can set values too — useful in tests or at boot:

```python
config().set("services.stripe.key", "sk_test_…")
config().has("services.stripe.key")   # True
```

!!! warning "Config is read-only at runtime"
    Treat configuration as **immutable once the app has booted**. `set()` exists for boot-time
    assembly and tests; the repository is not synchronised for concurrent writes, so mutating it
    while requests are in flight is a race. Read freely; write only during setup.

    For the same reason, `config().all()` returns a **deep-copy snapshot** — mutating it does not
    change the live config. Values returned by `config("some.key")` should be treated as read-only;
    don't mutate a dict or list you read back.

!!! note "Setting through a scalar creates a section"
    `set("a.b", 1)` when `a` is currently a scalar (say the string `"x"`) replaces that scalar with a
    new section `{"b": 1}` — the old value is discarded (a debug line is logged on the
    `arvel.config` logger). This is convenient but lossy; don't `set()` *into* a key you also use as
    a leaf value.

## Environment variables: `env()`

Configuration that differs per environment — or is secret — belongs in the environment, not in code.
Read it with `env()`:

```python
from arvel import env

env("APP_DEBUG")                   # the value, coerced (see below)
env("MAIL_PORT", 25)               # default when the variable is unset
```

`env()` applies **literal coercion** so common boolean/null spellings come back as real
Python values rather than strings:

| Env value (case-insensitive) | `env()` returns |
|---|---|
| `true`, `(true)` | `True` |
| `false`, `(false)` | `False` |
| `null`, `(null)` | `None` |
| `empty`, `(empty)` | `""` (empty string) |
| `"quoted"` or `'quoted'` | the inner text, **verbatim** — quotes are stripped and no coercion runs |
| anything else | the raw string, unchanged |

Wrapping quotes make a value literal: `KEY="true"` returns the string `"true"`, not `True` — quote a
value when you need it to survive coercion (or to keep leading/trailing spaces).

!!! warning "Coercion can surprise you"
    Coercion is **case-insensitive** and matches the *whole* value, so a variable whose literal value
    is `null` or `false` comes back as `None`/`False` — not the string. If a secret or token could
    legitimately be one of these words, don't rely on `env()` for it. Also note `env()` returns the
    raw **string** for everything else: `env("PORT")` is `"8000"`, not `8000`. To get a typed,
    validated value, use [typed settings](#typed-settings).

`env()` reads from the process environment (`os.environ`), which `.env` files feed at boot.

## Environment files

In development you keep environment variables in a `.env` file at the project root (never commit it —
it holds secrets). arvel loads it at boot via `load_dotenv`, parsed by
[python-dotenv](https://pypi.org/project/python-dotenv/), so the full `.env` syntax works:

```bash
# .env
APP_NAME="My App"          # quotes and inline comments are handled
export DATABASE_URL=postgres://localhost/app   # `export` prefix is fine
SECRET_KEY='a#literal#value'                    # special chars inside quotes are preserved
GREETING=Hello ${APP_NAME}                      # ${VAR} expansion
```

Three rules matter:

- **Real environment variables win.** Loading is no-override — if a variable is already set in the
  process environment (e.g. injected by your container/orchestrator in production), the `.env` value
  is ignored. This is what lets production override development defaults safely.
- **`${VAR}` is expanded.** python-dotenv interpolates `${OTHER}` references against the environment.
  If a secret's literal text contains a `$`, quote/escape it (`PASSWORD='a\$literal'`) so it isn't
  treated as a reference.
- **A missing `.env` is a no-op.** Production typically has no file and relies on real env vars.

Read the loaded values with `env()` or, for typed/validated access, [typed settings](#typed-settings).

## The config directory

For app-level configuration, put Python files in a `config/` directory at your project root. At boot
arvel auto-loads every `config/*.py` into the repository under the file's **stem** — so
`config/app.py` populates the `app.*` namespace, `config/database.py` populates `database.*`, and so
on. A file exposes its values either as a `config` mapping or as UPPERCASE module variables:

```python
# config/app.py
from arvel import env

config = {
    "name": env("APP_NAME", "arvel"),
    "env": env("APP_ENV", "local"),
    "debug": env("APP_DEBUG", False),
    "timezone": "UTC",
}
```

```python
config("app.name")        # "arvel" (or $APP_NAME)
config("app.debug")       # False (or the coerced $APP_DEBUG)
```

Because config files are plain Python, they can call `env()` to pull per-environment values (the
`.env` file is loaded *before* the config directory, so it's available here). Files whose name starts
with `_` are skipped (use them for shared helpers); a missing `config/` directory is fine.

!!! danger "Config files are executed"
    Loading a config file **runs it as Python** (that's how `env()` calls work) — it is not sandboxed.
    Only ever load config from a trusted project tree, never from an untrusted or user-supplied path;
    treat a config path with the same care as any code you import. Loaders restrict to `.py` files as
    light defense-in-depth, but the real boundary is *where the path comes from*.

Prefer a different location? `Application.configure(...)` has an override for each conventional
directory arvel looks for at your project root:

```python
Application.configure(base_path=".")
    .with_config_dir("settings")           # instead of {base_path}/config
    .with_public_dir("public")             # static/SPA front door — see Routing
    .with_lang_dir("resources/lang")       # instead of {base_path}/lang — see Localization
    .create()
```

### Precedence

When the same key is set in more than one place, the winner is, highest first:

1. **`with_config({...})`** / `config().set(...)` — explicit programmatic values always win.
2. **`config/*.py`** — your app's config files.
3. **Package defaults** — values a service provider contributes via `merge_config_from`.

In other words: programmatic config overrides your files, and your files override third-party package
defaults. Each layer only *fills gaps* the higher layers didn't set (deep-merged for nested dicts).

## Package configuration

Reusable packages ship their own config defaults and merge them under a namespace from a service
provider's `register()`, using `merge_config_from`:

```python
from pathlib import Path

class WidgetServiceProvider(ServiceProvider):
    def register(self) -> None:
        self.merge_config_from({"size": "L", "color": "red"}, "widget")
        # or from a file shipped beside the provider:
        self.merge_config_from(str(Path(__file__).parent / "config" / "widget.py"), "widget")
```

**Existing app values always win.** If the app has already configured the namespace, the package's
defaults only fill the gaps — the app's values are never overwritten:

- App set `config["widget"] = {"size": "S"}` → result `{"size": "S", "color": "red"}` (the
  package's `color` is merged in; the app's `size` wins).
- App set `config["widget"] = "custom"` (a deliberate **scalar** override) → result stays `"custom"`;
  the defaults do not clobber it.

The merge is deep (nested dicts are merged recursively) and copies the package defaults, so a
provider's module-level default constant is never mutated by later runtime changes.

## Typed settings

`config()` is dynamic and untyped. When you want a **validated, typed** handle on a *section* of it —
with defaults, coercion, and IDE autocomplete — define a `Settings` subclass, point its
`__config_key__` at a config section, and **just instantiate it**. Crucially, this is a **typed view
over `config()`, not a second config source**: the values come from the one pipeline (config files /
`with_config` / env via config files), so a typed setting can never disagree with `config()`. It's
built on [msgspec](https://jcristharif.com/msgspec/) (core, fast, no extra dependency; pydantic is
intentionally not used — see DR-0005/DR-0016):

```python
from arvel.kernel import Settings

class BillingSettings(Settings):
    __config_key__ = "billing"     # the config() section this maps to
    currency: str = "usd"
    trial_days: int = 14
    dunning: bool = False

billing = BillingSettings()    # reads + validates config("billing")
billing.trial_days             # int, coerced (e.g. "30" → 30) — and == config("billing.trial_days")
billing.dunning                # bool, coerced from the config value
```

Instantiating reads the `billing` section from `config()`; absent fields fall back to the struct's
defaults, a missing section yields all-defaults, and **explicit keyword args override the section**
(`BillingSettings(trial_days=30)`). Values are coerced and **validated** through `msgspec.convert` — a
bad value (e.g. `trial_days` set to `"soon"`) raises `msgspec.ValidationError`, so misconfiguration
fails fast rather than surfacing as a confusing error later.

```python
import msgspec

try:
    BillingSettings()
except msgspec.ValidationError:
    ...  # config("billing.trial_days") wasn't a valid integer
```

With no application running (a pure unit test), instantiation skips the config read and uses defaults
plus any explicit kwargs — so `BillingSettings(trial_days=30)` is a plain, app-free way to build one.

!!! tip "One source of truth"
    `Settings` deliberately does **not** read the environment itself — that would be a second config
    path competing with `config()`. Put your environment reads in a `config/*.py` file (`env(...)`),
    and let `Settings` give you a typed, validated lens over the result.

The framework's own modules ship typed settings built this exact way:
`MailSettings` (`mail`, with a nested `SmtpSettings` for host/port/auth/encryption), `CacheSettings`,
`DatabaseSettings`, `SessionSettings` (`session`), `FilesystemSettings`, `BroadcastingSettings`,
`SearchSettings`, `ViewSettings`, and `AppSettings` (`app`). So a bad `mail.smtp.port` or
`session.lifetime` fails fast at startup. Define your own for your app's sections the same way.

!!! note "The `app` section has both a typed view and raw reads"
    `AppSettings` gives you a typed view of `app.*`, but a few of the framework's *own* foundational
    reads (`app.timezone` in `arvel.dates`, `app.name` in `arvel.contracts`) stay on raw `config()` —
    those modules sit below the settings layer in the import graph and can't depend on it.

## Common mistakes & gotchas

- **Keys can't contain literal dots.** A dotted key is *always* a path: `config("a.b")` reads `b`
  inside `a`. There's no way to address a single key literally named `"a.b"`.
- **`env()` returns strings.** Apart from the literal-coercion table above, `env("PORT")` is the
  string `"8000"`, not the integer `8000`. For typed, validated values use a `Settings` subclass.
- **A value that looks like a literal is coerced.** `env()` turns `null`/`false`/`true`/`empty`
  (any case) into `None`/`False`/`True`/`""`. Don't store a secret whose literal text is one of these
  and expect the string back.
- **Don't mutate what you read.** `config(...)` may hand back the live nested structure; treat it as
  read-only and use `set()` to change config (and only at boot — see the read-only warning above).
- **Config holds secrets.** The repository's `repr()` redacts values for exactly this reason — don't
  log `config().all()` or individual secret values yourself.
