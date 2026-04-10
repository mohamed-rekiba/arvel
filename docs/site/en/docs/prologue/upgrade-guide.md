# Upgrade Guide

Upgrading Arvel should feel like upgrading any well-behaved SemVer library: read the release notes, bump the version, run the test suite, and fix what breaks. Because the framework touches routing, the container, providers, and the ORM, give yourself a clean branch and a full `pytest` run whenever you cross a minor or major boundary — not just a patch.

## General steps

1. **Pin the new version** in `pyproject.toml` (or let your lockfile tool resolve it) and refresh your lockfile if you use one.
2. **Read** [Release Notes](release-notes.md) and the [CHANGELOG](https://github.com/mohamed-rekiba/arvel/blob/main/CHANGELOG.md) for your target version and everything between your current pin and the new one.
3. **Sync dependencies** (for example with `uv sync --all-extras` in this repo) so optional integrations match the core version.
4. **Run tests** — project tests first, then a quick smoke of HTTP, CLI, and any database migrations you maintain.
5. **Search the codebase** for deprecations mentioned in the changelog; replace APIs before they disappear in the next major.

Confirm the resolved package version in your environment:

```python
from importlib import metadata

assert metadata.version("arvel").startswith("0.1.")
```

Adjust the expected prefix when you target a different release line.


## v0.1.0

This is the first release — there's nothing to upgrade from. Install Arvel and start building.

If you run into issues, check the [CHANGELOG](https://github.com/mohamed-rekiba/arvel/blob/main/CHANGELOG.md) and open a discussion or issue on the repository so we can turn the answer into documentation for the next person.
