# ADR-136: Config files override env via a pydantic-settings source

**Date**: 2026-06-03
**Status**: Accepted

## Context

Arvel had two config systems that didn't talk to each other: the typed
`ArvelSettings` classes (which every provider consumes) read straight from env,
while `config/*.py` files were only reachable through the `config()` / `lookup()`
dotted accessor. A project could ship `config/database.py` and the
`DatabaseServiceProvider` would never look at it — the file was inert.

We want config files to be the source of truth, layered over env and defaults,
for **every** service, with a uniform rule:

```
explicit kwargs > config/*.py > environment variable > field default
```

The config files are map-shaped (Laravel `connections`/`stores`/`disks` with a
`default` selector), while the typed classes are single-active-shaped (flat
fields for the one active connection).

## Decision

Add `ConfigFileSettingsSource`, a `PydanticBaseSettingsSource`, and insert it
above the env source in `ArvelSettings.settings_customise_sources`. A class opts
in by declaring `__config_path__` — a dotted path into the config-module
registry. A `{default}` token resolves against `<stem>.default` so the file's
`default` selects the named entry that maps onto the class (faithful Laravel
named-entry model — "Path A"). The active name is surfaced on a `connection`
field when present.

The source returns only keys matching the model's fields; everything else falls
through to env. Classes without `__config_path__` are untouched.

`dump_config_cache` strips secret-named keys before writing the config cache, so
the cascade doesn't turn `bootstrap/cache/config.json` into a credential leak.

## Alternatives Considered

1. **Flatten the config files** to match the flat typed classes — rejected;
   breaks Laravel parity and drops the named-connections capability.
2. **Provider-level glue** that reads `config()` and passes values into each
   manager — rejected; repeats the same plumbing per provider and bypasses
   pydantic validation.
3. **Replace typed classes with raw dict lookups** — rejected; loses static
   types and validation at the boundary.

## Consequences

- **Positive**: One uniform precedence rule across all services; config files
  finally drive providers; named connections/stores/disks become real.
- **Positive**: No per-provider plumbing — the hook is in the base class.
- **Negative**: Loading a `config/*.py` now changes resolution globally; a
  shipped example file (e.g. the skeleton's `database.py`) becomes authoritative.
  Mitigated by the per-service regression test matrix.
- **Negative**: URL-embedded credentials aren't detected by the cache redactor;
  documented — keep secrets in discrete keys.
