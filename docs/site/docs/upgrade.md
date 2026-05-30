# Upgrade Guide

This page documents breaking changes and migration steps for each Arvel release. We try hard to keep breaking changes minimal — if a change requires updating your code, you'll find it here with before/after examples.

## Versioning policy

Arvel follows [Semantic Versioning](https://semver.org) from `1.0.0` onward. Until then, `0.x` minor releases may include breaking changes, always documented below.

## Upgrading to 0.3.0

**Estimated upgrade time: under 30 minutes for most apps.**

### Python 3.14 required

Arvel `0.3.0` requires Python 3.14+. If you're on 3.12 or 3.13, upgrade first:

```bash
uv python install 3.14
```

Then update your `.python-version` file and your `pyproject.toml`:

```toml
[project]
requires-python = ">=3.14"
```

### Dependency update

```bash
uv lock --upgrade-package arvel
uv sync
```

### Config class changes

`ArvelSettings` now reads `env_prefix` automatically from the class name (snake-cased, with a trailing `_`). If you previously set `model_config = SettingsConfigDict(env_prefix="DB_")` explicitly, that still works — the auto-derive is only a fallback.

### Auth: `AuthServiceProvider` now required

The auth subsystem is no longer auto-loaded. You must register `AuthServiceProvider` explicitly in `bootstrap/providers.py`:

```python
from arvel.auth import AuthServiceProvider

PROVIDERS = [
    AuthServiceProvider,
    # ... your other providers ...
]
```

If you used `arvel auth:install` to scaffold auth, the generated `bootstrap/providers.py` already includes this.

### Queue: retry semantics

`Job.tries` previously counted the initial attempt. It now counts retries only — so `tries = 3` means up to 3 retries after the first failure (4 total attempts). If you relied on the old semantics, subtract 1 from your `tries` value.

---

## Upgrading to 0.1.0

`0.1.0` was the first public release. No upgrade path from pre-release versions is documented.

## Next steps

- Read [Release Notes](releases.md) for a full list of what shipped in each version.
- Check [Configuration](configuration.md) if any environment variables changed.
