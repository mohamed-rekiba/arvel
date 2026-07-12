# Documentation-driven gap register

Found while rewriting the docs section by section: features the reference framework's
documentation covers that arvel doesn't implement (or implements partially). Nothing here is
documented as working — each entry is a candidate for a decision (build / wontfix / defer).

| # | Section | Gap | Reference equivalent | Suggested remediation |
|---|---------|-----|----------------------|-----------------------|
| G-01 | Getting Started | The globally-installed CLI crashes with a raw `ModuleNotFoundError` when a project command (e.g. `shell`) runs inside a project whose deps live in its own venv | The reference's global installer is used only to create projects; per-project commands run through the app-local entrypoint, so the mismatch can't happen | Detect the situation (in a project + import failure of an app dependency) and exit with a clear "run this from your project's environment (`source .venv/bin/activate`)" message instead of a traceback |
| G-02 | Getting Started | Scaffold profiles (`api`/`web`/`inertia-vue`/`minimal` + `--auth`) cover app shape, but there is no full starter-kit tier (auth pages + frontend scaffolding + profile UI as one kit) | First-party starter kits ship complete auth/frontend starting points | Decide whether profiles+`--auth` are the intended ceiling; if not, grow a `--kit` tier or document profiles as the equivalent |
