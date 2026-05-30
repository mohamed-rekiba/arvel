# ADR-069 — Resolve the `arvel` console-script collision: rename `arvel-cli`'s script to `arvel-new`

**Status**: Superseded
**Date**: 2026-05-19
**Supersedes**: none
**Superseded by**: [ADR-075](ADR-075-single-arvel-binary-consolidation.md)
**Related**: ADR-068 (CLI framework bootstrap), `packages/arvel-cli/pyproject.toml`

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
# framework's "arvel" binary. See ADR-069.
arvel-new = "arvel_cli.cli:main"
```

The framework's `arvel` script (`arvel.console.entrypoint:main`) detects when it's run outside a project (no `bootstrap/app.py` in cwd-or-up-to-4-ancestors per ADR-068) AND the requested subcommand isn't in the "always allowed" set (`--help`, `--version`, `about`, `make:*`, `key:generate`). When that happens, it prints:

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
