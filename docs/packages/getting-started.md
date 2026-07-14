# Packages: Getting Started

Everything arvel ships — mail, cache, queues — is built on the same extension
points your package gets. This page takes you from an empty directory to a
published package that any arvel app can `uv add` and use with **zero wiring**:
installing it auto-registers your service provider through the
`arvel.providers` entry point.

The skeleton is **maximal-subtractive**: every contribution type a package can
make is already there — the working ones as small examples, the rest as
commented verbs — and you delete what you don't need. An un-pruned skeleton
boots and passes its own CI before you touch a single file, so you always start
from green.

## 1. Generate

```bash
arvel new payments --package
cd payments && uv sync
uv run pytest        # green before you change anything
```

You get a complete package: `pyproject.toml` (entry point + extras +
strict-mypy + import-linter), a provider with every integration verb, a
Manager/driver pair with a **fake driver**, a facade, an example route and
console command, a test suite with a booted-app fixture, and CI + PyPI-release
workflows.

## 2. Prune

Open `README.md` in the generated package — it carries the keep/delete table.
Rule of thumb: keep `pyproject.toml`, `provider.py`, `config.py`, `tests/`, and
CI; delete any of manager/drivers, facade, routes, or commands your package
doesn't need. Deleting a file and its provider line is the whole operation.

## 3. Build

Replace the example driver with your real one. The two disciplines that keep a
package healthy:

- **Depend on arvel's shape, not its guts.** Import from `arvel.contracts` and
  the public API only — then a framework refactor can't break you.
  ([Package Development](development.md) covers why.)
- **Heavy engines stay off the import path.** Lazy-import your engine inside
  the driver method that uses it, give it an extra in `pyproject.toml`, and
  list it in the import-linter contract. A missing engine then fails with
  `uv add 'arvel-payments[stripe]'` — the fix in the message — because your
  Manager sets `extra_package = "arvel-payments"`.

Test against a bare `Application()` — the generated `tests/conftest.py` fixture
registers and boots your provider in-process, no host app or `pip install`
needed. Your users test *their* code against your package the same way they
test mail: `Payments.fake()` swaps in your fake driver and they assert on calls.

## 4. Wire more contributions

`provider.py` documents every verb inline; uncomment to activate:

| Verb | Contributes |
|---|---|
| `merge_config_from` | config defaults (host app values win) |
| `load_routes_from` | HTTP routes (see the example `routes.py`) |
| `load_migrations_from` | migrations run with the app's own |
| `load_views_from` / `load_translations_from` | namespaced views / translations |
| `commands(...)` | console commands |
| `publishes(...)` | files the app copies out via `arvel vendor:publish` |
| `provides()` | marks the provider **deferred** — zero boot cost until first use |

## 5. Publish

Tag `v0.1.0` and push — `release.yml` builds and publishes to PyPI via trusted
publishing (configure the publisher once on pypi.org, no token secrets). Any
arvel app is now one `uv add arvel-payments` away from your provider
registering itself.

## Common mistakes & gotchas

- **Forgetting the entry point** — a renamed provider class must be updated in
  `pyproject.toml` under `arvel.providers`, or nothing registers (silently).
- **Route files wire in `register()`, not `boot()`** — the app loads route
  files right after provider registration; the async boot loop runs later, so
  a `boot()`-time `load_routes_from` silently misses the window. And because
  route files load by path, use absolute imports inside them.
- **A top-level heavy import** — breaks the host app's startup guarantee; the
  generated import-linter contract fails your CI first. Keep engines inside
  driver methods.
- **Testing through your own wiring instead of the provider** — the fixture
  boots the provider exactly as a host app would; if a binding only works when
  your test constructs it by hand, real apps are broken.

## See also

- [Package Development](development.md) — the extras model, entry-point
  discovery, and why `import arvel` stays light.
- [Service Providers](../providers.md) — every integration verb in depth.
