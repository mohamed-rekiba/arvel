# ADR-126 — Consolidate the CLI into a single `arvel` binary (delete `arvel-cli`)

**Status**: Accepted
**Date**: 2026-05-20
**Supersedes**: [ADR-126](ADR-126-single-arvel-binary-consolidation.md)
**Superseded by**: none
**Related**: ADR-005 (canonical app layout), ADR-121 (CLI packaging), ADR-123 (CLI framework bootstrap)

## Context

ADR-126 picked a two-binary split to resolve the `[project.scripts] arvel` collision between `packages/arvel` (framework CLI) and `packages/arvel-cli` (scaffolder). The framework kept `arvel`; the scaffolder was renamed to `arvel-new` and shipped from a separate PyPI distribution.

A few months in, the two-binary split is paying negative dividends:

- Users have to install **two** things (`uv tool install arvel-cli` for the scaffolder, then `arvel` arrives transitively when they `uv sync` inside the project). The split shows up in the install path (`install.sh` / `install.ps1`), the docs (`installation.md`, `starter-kits.md`, every "getting started" page), and the badges (two PyPI badges in the README).
- The scaffolder duplicates infrastructure the framework already has: name validation, templating, Typer wiring, an `Application` shell — without sharing types or tests with the framework.
- The release pipeline carries two parallel tracks: two `release-please` components, two PyPI Trusted Publishers, two SBOMs, two CycloneDX exports, two `uv build` invocations, two `twine check` calls.
- Users discover `arvel-new` only through docs. Once they're inside a project, `arvel` is the entry point — `arvel-new` is no longer needed and clutters their `~/.local/bin`.
- The framework already gates its in-project commands behind `find_project_root()` (ADR-123). Allowing one more name (`new`) in the outside-project allow-list and registering it as an entry-point is a one-line change.

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
- Users coming from ADR-126-era docs need to retrain their fingers: `arvel new my-app` (with a space) replaces `arvel-new my-app`.

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

- ADR-005 — canonical app layout (the skeleton is the on-disk shape of this ADR)
- ADR-121 — CLI packaging (replaced by this ADR for the "where does the scaffolder live" question)
- ADR-123 — CLI framework bootstrap (the outside-project gate that `new` plugs into)
- ADR-126 — the two-binary split, now superseded by this ADR
- `packages/arvel/src/arvel/console/commands/new.py` — the new command
- `packages/arvel/src/arvel/_skeleton/` — the packaged project skeleton

---

## Merged: Resolve the `arvel` console-script collision: rename `arvel-cli`'s script to `arvel-new` (was ADR-126)

**Status**: Superseded
**Date**: 2026-05-19
**Supersedes**: none
**Superseded by**: [ADR-126](ADR-126-single-arvel-binary-consolidation.md)
**Related**: ADR-123 (CLI framework bootstrap), `packages/arvel-cli/pyproject.toml`

## Context

Two packages each declare a `[project.scripts]` entry named `arvel`:

- `packages/arvel/pyproject.toml` → `arvel = "arvel.console.entrypoint:main"` (the framework binary).
- `packages/arvel-cli/pyproject.toml` → `arvel = "arvel_cli.cli:main"` (the scaffolder, used as `arvel new my-app`).

When a user runs `pip install arvel arvel-cli`, whichever wheel installs the script last wins. The user ends up with EITHER the scaffolder OR the framework — not both. The other binary is silently replaced. Even worse, the failure mode is invisible until the user tries to run `arvel migrate` and gets "command not found" or "scaffolder-like behaviour".

Three approaches were considered.

### Options

**Option 1 — Single binary with subcommand routing.** Make `arvel` always be the framework's entrypoint; merge the scaffolder's `new` subcommand into the framework as a built-in. Pro: one binary, one mental model — closest to Laravel's `composer create-project` + `php artisan` split (where `composer` is a separate tool). Con: makes `arvel-cli` a dev-dependency of `arvel`, inverting today's dep direction; muddies the scaffolder/framework boundary that Article XI explicitly draws.

**Option 2 — Rename `arvel-cli`'s script to `arvel-new`.** Adjust `packages/arvel-cli/pyproject.toml` to `arvel-new = "arvel_cli.cli:main"`. Pro: clean separation maintained; install order doesn't matter; users run `arvel-new my-app` to scaffold and `arvel <whatever>` inside the project. Con: existing users with muscle memory for `arvel new` must update aliases/docs.

**Option 3 — Console-script-with-namespace** (e.g., `arvel cli new` invokes scaffolder). Pro: keeps "arvel" as the only binary. Con: requires the framework's `arvel` to know about the scaffolder, or vice versa; same coupling problem as Option 1 with extra indirection.

## Decision

**Option 2 — rename `arvel-cli`'s console script to `arvel-new`** AND add an outside-project wrapper inside the framework's `arvel` script that detects when the user is running commands outside a project directory.

### Concrete change

`packages/arvel-cli/pyproject.toml`:

```toml
[project.scripts]
# WI-021: renamed from "arvel" to "arvel-new" to resolve console-script collision with the
# framework's "arvel" binary. See ADR-126.
arvel-new = "arvel_cli.cli:main"
```

The framework's `arvel` script (`arvel.console.entrypoint:main`) detects when it's run outside a project (no `bootstrap/app.py` in cwd-or-up-to-4-ancestors per ADR-123) AND the requested subcommand isn't in the "always allowed" set (`--help`, `--version`, `about`, `make:*`, `key:generate`). When that happens, it prints:

```
No Arvel project found. To create a new project:
  arvel-new <name>   (install: pip install arvel-cli)
To run a command outside a project, use arvel make:* or arvel about.
```

…and exits 2. This gives a user who runs `arvel migrate` outside a project a discoverable migration path to the new command name without them having to read release notes.

### Install scripts and skeleton docs

`scripts/install.sh`, `scripts/install.ps1`, the scaffolder skeleton's `README.md.tmpl`, and `docs/strategy/constitution.md` references all switch to `arvel-new` for any example invocations of the scaffolder.

## Consequences

**Positive:**

- `pip install arvel arvel-cli` works regardless of install order — both binaries are reachable.
- Clean separation between scaffolder (`arvel-new`, lives in `packages/arvel-cli`) and framework (`arvel`, lives in `packages/arvel`).
- Outside-project wrapper gives existing `arvel new` users a clear, discoverable migration path.
- No coupling between framework and scaffolder beyond what already exists (skeleton's `Makefile` references `arvel` — that doesn't change; `arvel-new` only ever runs at scaffold time).

**Negative:**

- BREAKING for any user / CI script / shell alias that referenced `arvel new` (the scaffolder). CHANGELOG marks the WI-021 commit with the Conventional Commits `!` suffix and includes a migration line in the Unreleased section.
- One new gate added to `docs/dx/quality-gates.md` (#33 dual-install matrix CI job) to prevent future regression — CI fails if either binary becomes unreachable in either install order.

**Neutral:**

- The framework's `arvel` script binary path is unchanged; only its "outside project" behaviour is new.
- The naming `arvel-new` mirrors `create-react-app` / `create-vite-app` conventions familiar to JS devs and is short enough to type. Considered alternatives: `arvel-scaffold`, `arvel-init`, `mkarvel` — rejected for being longer or less discoverable.

## Implementation notes

- Test fixture in `packages/arvel-cli/tests/test_script_rename.py` asserts `which arvel-new` resolves after `uv pip install ./packages/arvel-cli` and that `which arvel` does NOT point to the scaffolder.
- Dual-install matrix CI job runs in fresh venvs, both `framework-first` and `scaffolder-first` orderings, asserting `arvel --version && arvel-new --help` both exit 0 (NFR-021-05).
- Constitution amendment NOT required — Article XI ("Scaffolder vs framework") already mandates separation; this ADR just makes the script names reflect the separation that was always intended.
