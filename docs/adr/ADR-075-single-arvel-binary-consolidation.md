# ADR-075 — Consolidate the CLI into a single `arvel` binary (delete `arvel-cli`)

**Status**: Accepted
**Date**: 2026-05-20
**Supersedes**: [ADR-069](ADR-069-arvel-script-collision.md)
**Superseded by**: none
**Related**: ADR-018 (canonical app layout), ADR-020 (CLI packaging), ADR-068 (CLI framework bootstrap)

## Context

ADR-069 picked a two-binary split to resolve the `[project.scripts] arvel` collision between `packages/arvel` (framework CLI) and `packages/arvel-cli` (scaffolder). The framework kept `arvel`; the scaffolder was renamed to `arvel-new` and shipped from a separate PyPI distribution.

A few months in, the two-binary split is paying negative dividends:

- Users have to install **two** things (`uv tool install arvel-cli` for the scaffolder, then `arvel` arrives transitively when they `uv sync` inside the project). The split shows up in the install path (`install.sh` / `install.ps1`), the docs (`installation.md`, `starter-kits.md`, every "getting started" page), and the badges (two PyPI badges in the README).
- The scaffolder duplicates infrastructure the framework already has: name validation, templating, Typer wiring, an `Application` shell — without sharing types or tests with the framework.
- The release pipeline carries two parallel tracks: two `release-please` components, two PyPI Trusted Publishers, two SBOMs, two CycloneDX exports, two `uv build` invocations, two `twine check` calls.
- Users discover `arvel-new` only through docs. Once they're inside a project, `arvel` is the entry point — `arvel-new` is no longer needed and clutters their `~/.local/bin`.
- The framework already gates its in-project commands behind `find_project_root()` (ADR-068). Allowing one more name (`new`) in the outside-project allow-list and registering it as an entry-point is a one-line change.

The scaffolder is a single Typer command (`new`) with three flags (`--no-install`, `--python`, `--help`). Carrying a dedicated package for that is the smallest unit of complexity, but it's still complexity. Cutting it out is a net subtraction.

### Options reconsidered

**Approach A — Move `arvel-cli` source into `packages/arvel/`, keep the separate distribution.** Same two PyPI packages, but `arvel-cli` becomes a thin wheel that depends on `arvel` and re-exports a Typer command. Pro: zero install-side change. Con: keeps every downside above (two release tracks, two SBOMs, two installs) and adds a circular concern (the scaffolder now imports from the framework it scaffolds).

**Approach B — Merge into a single `arvel` package.** Move the scaffolder's source, skeleton tree, and tests into `packages/arvel/`. Register `new` as a `[project.entry-points."arvel.commands"]` entry. Allow-list it in the outside-project gate. Delete `packages/arvel-cli/`. **(chosen)**

**Approach C — Keep two packages, leave the rename in place.** Status quo. Rejected: same downsides, no upsides.

## Decision

**Approach B.** Consolidate everything the user installs and runs into the single `arvel` PyPI package.

### Concrete changes

- **Sources moved**
  - `packages/arvel-cli/src/arvel_cli/_templating.py` → `packages/arvel/src/arvel/console/_scaffold/templating.py`
  - `packages/arvel-cli/src/arvel_cli/_validation.py` → `packages/arvel/src/arvel/console/_scaffold/validation.py`
  - `packages/arvel-cli/src/arvel_cli/skeleton/` → `packages/arvel/src/arvel/_skeleton/`
  - `packages/arvel-cli/src/arvel_cli/cli.py` → `packages/arvel/src/arvel/console/commands/new.py` (rewritten as an `arvel.console.Command` subclass; the Typer wiring matches the rest of the make:* commands)
- **New entry-point**
  ```toml
  [project.entry-points."arvel.commands"]
  "new" = "arvel.console.commands.new:NewCommand"
  ```
- **Outside-project allow-list** — `_OUTSIDE_PROJECT_ALLOWED_NAMES` in `arvel.console.entrypoint` now includes `"new"`. The migration hint message points at `arvel new` (one binary, one command).
- **Stale skeleton shim removed** — `packages/arvel/src/arvel/_skeleton/arvel` (the pre-WI-005 console-shim file) is deleted. The real `arvel` binary on the user's PATH supersedes it.
- **Tests** — moved to `packages/arvel/tests/console/scaffold/`. The two arvel-cli-only tests (`test_script_rename.py`, `test_smoke.py`) were obsolete after the merge and removed.
- **Package deleted** — `packages/arvel-cli/` is gone.
- **Workspace + tooling** — `tool.uv.workspace` (root `pyproject.toml`), `[tool.mypy]` paths/files, `[tool.pyright]` includes/extraPaths, `[tool.pytest.ini_options].testpaths`, `Makefile` `SRC` / `sbom` / `build` targets, and every CI workflow (`ci.yml`, `security.yml`, `release.yml`, `publish.yml`, `release-please-config.json`, `release-please-manifest.json`) all drop the `arvel-cli` track.
- **Installers** — `install.sh` and `install.ps1` install `arvel` (instead of `arvel-cli`). The "next steps" line is `arvel new my-app`.
- **Docs** — `installation.md`, `starter-kits.md`, `structure.md`, `artisan.md`, `releases.md`, `contributions.md`, `sail.md`, `pint.md`, `homestead.md`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/ops/README.md` all switched from the two-binary story (`arvel-cli` + `arvel-new`) to one-binary (`arvel new`).

### Consequences

**Positive**

- One install (`uv tool install arvel`), one binary, one mental model.
- Half as many wheels, SBOMs, release components, and CI jobs.
- Scaffolding shares the same `Command` machinery, name validator, and test harness as the rest of the CLI — no duplication.
- Bug-fix flow is shorter — one `pip install --upgrade arvel` updates both scaffolder and framework.

**Negative**

- Anyone who installed `arvel-cli` before this ADR has to uninstall it (`uv tool uninstall arvel-cli`) and install `arvel` instead. The `no-backward-compatibility.mdc` rule says no legacy aliases — there is no `arvel-new` shim. The migration is one paragraph in the changelog.
- Users coming from ADR-069-era docs need to retrain their fingers: `arvel new my-app` (with a space) replaces `arvel-new my-app`.

**Neutral**

- The packaged skeleton lives inside the framework's wheel via `importlib.resources.files("arvel").joinpath("_skeleton")`. Hatchling's default `[tool.hatch.build.targets.wheel].packages = ["src/arvel"]` includes the whole tree, so the skeleton ships untouched.

### Verification

End-to-end smoke test after the merge:

```bash
uv sync
uv run arvel --help                 # shows `new` alongside `migrate`, `route:list`, …
uv run arvel new test-app --no-install
cd test-app
uv sync
uv run arvel make:model Post       # in-project make: works
uv run arvel about                 # framework facts
```

All quality gates run clean: `make ci`, `make security`, plus the migrated `tests/console/scaffold/` suite.

## References

- ADR-018 — canonical app layout (the skeleton is the on-disk shape of this ADR)
- ADR-020 — CLI packaging (replaced by this ADR for the "where does the scaffolder live" question)
- ADR-068 — CLI framework bootstrap (the outside-project gate that `new` plugs into)
- ADR-069 — the two-binary split, now superseded by this ADR
- `packages/arvel/src/arvel/console/commands/new.py` — the new command
- `packages/arvel/src/arvel/_skeleton/` — the packaged project skeleton
