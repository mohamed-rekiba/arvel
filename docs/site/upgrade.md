# Upgrade Guide

This page documents breaking changes and migration steps between Arvel releases. When a change requires updating your code, you'll find it here with before/after examples.

<a name="pre-upgrade-checklist"></a>
## Pre-Upgrade Checklist

Before bumping `arvel` in any environment:

1. Read the target version in [Release Notes](releases.md) and [`CHANGELOG.md`](https://github.com/mohamed-rekiba/arvel/blob/main/CHANGELOG.md).
2. Run your test suite and `arvel openapi:validate` if you ship a typed client.
3. Update lockfiles (`uv lock --upgrade-package arvel` or equivalent).
4. Run pending migrations (`arvel migrate`) after deploy — never assume schema is current.
5. Re-export OpenAPI and regenerate frontend clients when routes or form requests changed.
6. Re-run `arvel config:cache` in production after config file changes.

<a name="versioning-policy"></a>
## Versioning Policy

Arvel follows [Semantic Versioning](https://semver.org) from `1.0.0` onward. Until then, `0.x` minor releases may include breaking changes — always documented below.

<a name="upgrading-to-0-3-0"></a>
## Upgrading to 0.3.0

**Estimated upgrade time: a few minutes.**

`0.3.0` is a drop-in upgrade from `0.1.0` — it's purely additive, with no breaking changes. Update the dependency and re-sync:

```bash
uv lock --upgrade-package arvel
uv sync
```

To pull every optional feature in one go (the recommended install), use the `all` extra:

```bash
uv add "arvel[all]"
```

Python 3.14+ has been required since `0.1.0` — no change there.

<a name="upgrading-to-0-1-0"></a>
## Upgrading to 0.1.0

`0.1.0` was the first public release. There's no documented upgrade path from pre-release versions.

<a name="how-to-read-this-guide"></a>
## How to Read This Guide

Each future release adds a section here. Breaking changes come with the exact code to change. A couple of conventions worth knowing now, so later migrations read clearly:

- **Service providers.** App-level providers are declared in `bootstrap/providers.py` as a `providers` list. Some subsystems are opt-in — for example, `AuthServiceProvider` powers [authentication](features/authentication.md#registering-the-provider) and the [`Gate`](features/authorization.md):

```python
# bootstrap/providers.py
from arvel.auth.provider import AuthServiceProvider

providers = [
    AuthServiceProvider,
    # ...your other providers...
]
```

- **Config classes.** `ArvelSettings` subclasses auto-derive their `env_prefix` from the class name (`DbConfig` → `DB_`). Set `model_config["env_prefix"]` explicitly to override.

<a name="next-steps"></a>
## Next Steps

- Read the [Release Notes](releases.md) for what shipped in each version, or [`CHANGELOG.md`](https://github.com/mohamed-rekiba/arvel/blob/main/CHANGELOG.md) for the full log.
- Check [Configuration](core-concepts/configuration.md) if any environment variables changed.
