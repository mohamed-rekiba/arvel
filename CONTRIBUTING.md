# Contributing to Arvel

Thanks for your interest in Arvel. The framework aims to give Python the Laravel-style developer experience without giving up `mypy --strict` and `pyright --strict`. Contributions that move in that direction are very welcome.

## Quick start

```bash
git clone https://github.com/<org>/arvel.git
cd arvel
make sync            # uv sync --all-extras
make ci              # lint + format-check + typecheck + coverage
```

You need Python 3.14+ and [uv](https://docs.astral.sh/uv/) 0.9+.

## Repository layout

```
packages/
  arvel/              # the framework + CLI scaffolder (PyPI: arvel)
    src/arvel/
      _skeleton/      # packaged project skeleton (used by `arvel new`)
      console/        # CLI infrastructure + every built-in command
      ...
    tests/
benchmarks/           # smoke + future micro-benchmarks
docs/
  architecture/       # SADs
  adr/                # decision records
  prd/                # product requirements
  pipeline/           # stage-log + handoffs (audit trail)
```

We use a uv workspace; a single virtualenv and lockfile.

## Workflow

1. **Open an issue first** for anything non-trivial. We use the SDLC pipeline (`docs/pipeline/`) and prefer to align scope before coding.
2. **Branch from `main`**. Use `feat/`, `fix/`, `docs/`, `refactor/`, `test/`, `chore/`, `ci/` prefixes.
3. **Conventional Commits** for every commit. Release Please uses commit messages to compute versions and the changelog.
4. **Run `make ci` before pushing.** All gates must pass locally.
5. **Open a PR.** Keep it under 400 lines where possible. Link the issue and reference any FR/NFR IDs.

## Coding standards

- `mypy --strict` and `pyright --strict` must both pass — no exceptions.
- `ruff check` and `ruff format` must be clean.
- New code needs tests. Aim for **≥ 90%** coverage on `arvel/` and prefer behavioral tests over implementation tests.
- Public API additions need:
  - An entry in `docs/api/foundations-api.md` (or its successor)
  - A test that imports the symbol via the public path
  - A docstring that explains *why*, not *what*
- Comment hygiene: see `.cursor/rules/111-comment-style.mdc`. Comments explain *why*; the code already says *what*.

## Security

If you spot a security issue, **do not open a public PR**. Follow [SECURITY.md](./SECURITY.md).

For non-security PRs, the security workflow (bandit, pip-audit, gitleaks, semgrep) runs automatically. Findings at **high** or **critical** severity block merge.

## Release process

Releases are fully automated via [Release Please](https://github.com/googleapis/release-please).

1. Merge Conventional Commits into `main`.
2. Release Please opens a release PR that bumps the affected package's version and updates `CHANGELOG.md`.
3. Merging that PR creates a GitHub Release, which triggers PyPI publishing via [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (no API tokens).
4. Each artifact is signed with Sigstore and accompanied by a CycloneDX SBOM.

Releases are tagged with the `arvel-vX.Y.Z` prefix.

## Getting help

- Architecture questions → check `docs/architecture/` and `docs/adr/` first
- Process questions → `docs/pipeline/` has the full SDLC trail
- Anything else → open a Discussion or join the dev chat (link in README)
