# Configuration

Arvel has **two** configuration systems that coexist. Knowing which is which avoids a lot of confusion when reading provider code.

**Source**: `packages/arvel/src/arvel/config/` — `settings.py`, `registry.py`, `repository.py`, `no_prefix.py`, `_lookup_registry.py`, `errors.py`.

| System | API | Backed by | Use for |
|---|---|---|---|
| **Class-based (typed)** | `ArvelSettings`, `@register`, `Config.of(Cls)` | container singletons | strongly-typed config sections read from env |
| **Module-based (Laravel-style)** | `config("app.timezone")`, `lookup("db.DEFAULT")` | `_REGISTRY` dict of loaded `config/*.py` | dotted-key lookups into config modules |

```mermaid
flowchart TB
    subgraph typed ["Class-based / typed"]
        AS["ArvelSettings subclass"] --> REG["@register / with_config_files"]
        REG --> CSP["ConfigServiceProvider.register()"]
        CSP --> SING["container.singleton(Cls)"]
        SING --> COF["Config.of(Cls) → typed instance"]
    end
    subgraph modular ["Module-based / dotted"]
        CDIR["with_config_dir('config/')"] --> LR["_lookup_registry.register(stem, module)"]
        LR --> CFG["config('stem.key') / lookup('stem.key')"]
        CACHE["bootstrap/cache/config.json"] -.->|load_from_cache| LR
    end
```

## Class-based config (`ArvelSettings`)

`ArvelSettings` extends pydantic-settings `BaseSettings` with Arvel defaults:

```python
class ArvelSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        secrets_dir=None,
    )
```

Define a config section as a subclass:

```python
@register
class DbConfig(ArvelSettings):
    url: str = "postgresql+asyncpg://localhost/app"
    password: SecretStr = SecretStr("")
    # env prefix auto-derived: reads DB_URL, DB_PASSWORD
```

### Env-prefix auto-derivation

When a subclass doesn't set a non-empty `env_prefix`, `__init_subclass__` derives one from the class name: strip a trailing `Settings`/`Config` suffix, convert CamelCase to `SNAKE_`, append `_`.

```python
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SUFFIXES = ("Settings", "Config")

def _derive_prefix(class_name: str) -> str:
    name = class_name
    for suffix in _SUFFIXES:
        if name.endswith(suffix) and name != suffix:
            name = name[: -len(suffix)]
            break
    snake = _CAMEL_BOUNDARY.sub("_", name).upper()
    return f"{snake}_" if snake else ""
```

| Class | Derived prefix | Reads |
|---|---|---|
| `AppSettings` | `APP_` | `APP_*` |
| `MyThingConfig` | `MY_THING_` | `MY_THING_*` |
| `DbConfig` (sets `DB_` explicitly) | `DB_` | `DB_*` |

The built-in sections (`DbConfig`, `CacheConfig`, `SessionConfig`, `StorageConfig`, …) set an explicit `env_prefix`, so derivation is skipped for them.

### `NoPrefix`: opt a field out of the prefix

Wrap a field type in `Annotated[..., NoPrefix]` to read it from the bare uppercase env var instead of `{PREFIX}FIELD`:

```python
class AppSettings(ArvelSettings):
    name: str = "Arvel"                          # reads APP_NAME
    secret_key: Annotated[str, NoPrefix] = ""    # reads SECRET_KEY, not APP_SECRET_KEY
```

`__pydantic_init_subclass__` scans field metadata for the `NoPrefix` marker and rewrites the field's `validation_alias` to `AliasChoices(UPPER, field_name)`, then rebuilds the model.

### Registration and eager loading

```mermaid
sequenceDiagram
    participant Dev
    participant Reg as config/registry._REGISTERED
    participant CSP as ConfigServiceProvider
    participant C as Container

    Dev->>Reg: @register DbConfig  (or with_config_files)
    Note over CSP: bootstrap register phase
    CSP->>C: Config.bind(container)
    loop each registered class
        CSP->>C: container.singleton(Cls)
    end
    Note over CSP: bootstrap boot phase
    loop each registered class
        CSP->>C: container.make(Cls)  (eager — fails fast on bad env)
    end
```

`@register` appends a class to module-level `_REGISTERED`. `Application.with_config_files([...])` does the same per class. `ConfigServiceProvider.register()` binds `Config` to the container and registers a singleton per class; its `boot()` eagerly resolves each so invalid environment values fail at boot, not at first use.

### Reading typed config: `Config.of`

```python
class Config:
    _container: ClassVar[Container | None] = None

    @classmethod
    def bind(cls, container: Container) -> None:
        cls._container = container

    @classmethod
    def of(cls, settings_cls: type[T]) -> T:
        if cls._container is None or not cls._container.bound(settings_cls):
            raise ConfigNotRegisteredError(settings_cls)
        return cls._container.make(settings_cls)
```

`Config.of(DbConfig)` returns the singleton instance — fully typed, no string keys. `Config` is defined in `config/repository.py` but re-exported as a facade from `facades/__init__.py`.

## Module-based config (`config()` / `lookup()`)

This is the Laravel-style dotted accessor for `config/*.py` files loaded via `ApplicationBuilder.with_config_dir()`. Modules are stored in a process-wide registry keyed by file stem:

```python
_REGISTRY: dict[str, object] = {}   # reset at the start of each .create()

def register(stem: str, module: object) -> None:   # module-internal
    _REGISTRY[stem] = module
```

`lookup(key)` splits a dotted key, finds the module by its first segment, then walks attributes (falling back to dict subscript). It raises `ConfigKeyError` on any miss. `config(key, default=...)` wraps `lookup` and never raises — a missing key returns the default (or `None`):

```python
config("app.timezone")              # -> value, or None if missing
config("app.timezone", "UTC")       # -> value, or "UTC"
lookup("app.timezone")              # -> value, or raises ConfigKeyError
```

### Config caching

`with_config_dir` uses `{base_path}/bootstrap/cache/config.json`. On boot it resets the registry; if the cache exists and loads cleanly it skips importing `config/*.py`. The `config:cache` and `optimize` CLI commands write the cache via `dump_config_cache`; cached entries deserialize into `SimpleNamespace` objects.

Only the **module-based** registry is cached. Class-based `ArvelSettings` are resolved live from env on each `container.make()`.

> **Note**: `.gitignore` lists `.config_cache`, but no code under `config/` references it — the active cache file is `bootstrap/cache/config.json`. The `.config_cache` entry looks stale.

## Errors

| Exception | When |
|---|---|
| `ConfigNotRegisteredError` (subclass of `ConfigError`) | `Config.of(Cls)` for a class not bound to the container |
| `ConfigError` | A Pydantic `ValidationError` while loading an `ArvelSettings` (via `from_environment`), or any failure during `ConfigServiceProvider.boot()` eager load |
| `ConfigKeyError` | Empty key, unknown module stem, or unresolvable segment in `lookup()` |

> A separate `ConfigurationError` (a `ValueError` subclass in `config/exceptions.py`) is used for `ObservabilityConfig` field validation. It is unrelated to `Config.of()` / `config()`.

## See also

- [Facades](facades.md) — `Config` is one.
- [Bootstrap & lifecycle](bootstrap-lifecycle.md) — when config is loaded relative to providers.
