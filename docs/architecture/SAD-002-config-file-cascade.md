# SAD-002 — Config-file cascade for all services

**Work Item**: WI-arvel-002 | **PRD**: `docs/prd/PRD-002-config-file-cascade.md`
**Related ADRs**: ADR-021 (config files override env via a pydantic-settings source)

---

## Overview

Bridge the two config systems with one new pydantic-settings source. The typed
classes keep their shape and validation; they just gain a higher-priority source
that reads the loaded `config/*.py` modules. No per-provider plumbing.

## Components touched

| Component | Change |
|---|---|
| `config/_config_file_source.py` (new) | `ConfigFileSettingsSource` — reads `__config_path__` from the registry |
| `config/settings.py` → `ArvelSettings` | `__config_path__` ClassVar + `settings_customise_sources` inserting the source above env |
| `config/storage_config.py` | `__config_path__` on `StorageConfig` + the four disk configs |
| `config/db_config.py`, `config/cache_config.py` | `__config_path__` with `{default}` token |
| `queue/config.py`, `config/session_config.py`, `broadcasting/config.py` | `__config_path__` |
| `config/_lookup_registry.py` → `dump_config_cache` | strip secret-named keys before writing |

## Precedence

`settings_customise_sources` returns sources in priority order:

```
init (kwargs) > ConfigFileSettingsSource > env > dotenv > secrets > defaults
```

## Source flow

```
path = __config_path__
if "{default}" in path:
    sel = config("<stem>.default");  if not a non-empty str -> return {}   # fall back to env
    path = path.replace("{default}", sel)
data = as_mapping(config(path))                  # dict | module | namespace -> dict
result = {k: v for k, v in data if k in model_fields}
if "connection" in fields and not set:           # surface the active name
    result["connection"] = sel or config("<stem>.default")
return result
```

- `as_mapping` accepts plain dicts and module/`SimpleNamespace` objects (so the
  cache-loaded `SimpleNamespace` path works identically — FR-5).
- Only model-field keys are returned; extras fall through to env.

## Secret redaction (NFR-1)

`dump_config_cache` recurses the payload and drops keys matching
`password`/`passwd`/`secret`/`token`/`credential`/`private` or bare `key`.
Dropped keys resolve from env at load time.

## Threat model (abridged)

| Threat | Mitigation |
|---|---|
| Credentials persisted to `bootstrap/cache/config.json` | Secret-key redaction in `dump_config_cache` |
| URL-embedded credentials in cache | Documented caveat; not auto-detected |
| Unexpected config-file activation changing behavior | Per-service regression test matrix |

## Test coverage

- `tests/config/test_config_file_source.py` — mechanism + precedence + `{default}`.
- `tests/config/test_config_cascade_services.py` — storage/db/cache wiring.
- `tests/console/test_config_cache.py::TestSecretRedaction` — cache redaction.
