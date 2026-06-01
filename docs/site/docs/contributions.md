# Contribution Guide

Thanks for your interest in Arvel. The goal is to give Python the Laravel-style developer experience without giving up `mypy --strict` and `pyright --strict`. Contributions that move in that direction are very welcome.

<a name="quick-start"></a>
## Quick Start

```bash
git clone https://github.com/mohamed-rekiba/arvel.git
cd arvel
make dev    # uv sync --all-packages --all-extras
make ci     # lint + format-check + typecheck + coverage + docs
```

You need Python 3.14+ and [uv](https://docs.astral.sh/uv/). The repo is a uv workspace — one virtualenv, one lockfile.

<a name="repository-layout"></a>
## Repository Layout

```
packages/
  arvel/                 # the framework + CLI (PyPI: arvel)
    src/arvel/           # facades, ORM, HTTP, queue, events, console, …
      _skeleton/         # project skeleton used by `arvel new`
    src/arvent/          # the ORM package
    tests/
  arvel-oauth/           # OAuth2 / OIDC social login
  arvel-permission/      # roles & permissions
  arvel-image/           # image manipulation + media library
  arvel-search/          # full-text search
  arvel-audit/           # audit trails & activity logs
  arvel-ecommerce-demo/  # reference app
benchmarks/              # smoke + micro-benchmarks
docs/
  site/                  # this user-facing docs site (MkDocs)
  architecture/ adr/ prd/ pipeline/  # design + audit trail
```

<a name="workflow"></a>
## Workflow

1. **Open an issue first** for anything non-trivial — align on scope before coding.
2. **Branch from `main`** with a `feat/`, `fix/`, `docs/`, `refactor/`, `test/`, `chore/`, or `ci/` prefix.
3. **Use [Conventional Commits](https://www.conventionalcommits.org)** for every commit — Release Please reads them to compute versions and the changelog.
4. **Run `make ci` before pushing.** Every gate must pass locally.
5. **Open a PR.** Keep it under 400 lines where you can, and link the issue.

<a name="coding-standards"></a>
## Coding Standards

- `mypy --strict` and `pyright --strict` must both pass — no exceptions.
- `ruff check` and `ruff format` must be clean.
- New code needs tests. Coverage gates at **90%**; prefer behavioral tests over implementation tests.
- A public API addition needs an entry in the relevant doc, a test that imports it via its public path, and a docstring that explains *why*, not *what*.
- Comments explain *why* — the code already says *what*.

<a name="security"></a>
## Security

Spotted a security issue? **Don't open a public PR.** Follow [SECURITY.md](https://github.com/mohamed-rekiba/arvel/blob/main/SECURITY.md).

For everything else, the security workflow (bandit, pip-audit, gitleaks, semgrep) runs automatically. Findings at **high** or **critical** severity block the merge.

<a name="release-process"></a>
## Release Process

Releases are automated with [Release Please](https://github.com/googleapis/release-please):

1. Merge Conventional Commits into `main`.
2. Release Please opens a release PR that bumps the version and updates `CHANGELOG.md`.
3. Merging it creates a GitHub Release, which publishes to PyPI via [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) — no API tokens.
4. Each artifact is signed with Sigstore and ships with a CycloneDX SBOM.

Releases are tagged with the `arvel-vX.Y.Z` prefix.

<a name="getting-help"></a>
## Getting Help

- Architecture questions → start with the architecture docs and ADRs.
- Process questions → the pipeline audit trail has the full SDLC record.
- Anything else → open a GitHub Discussion.
