# Conventions

Patterns that recur across the codebase. Following them keeps new code consistent with the framework and clean under the gates.

**Source**: `CONTRIBUTING.md`, root `pyproject.toml`, and recurring patterns across `packages/arvel/src/arvel/`.

## Types

- Annotate everything. `mypy --strict` and `pyright --strict` (all `report*` as errors) both have to pass.
- Prefer precise types: `Sequence`/`Mapping` over `list`/`dict` in signatures, `Literal` for fixed sets, `Protocol` for driver/duck-typed contracts, `TypeVar`/`Generic` for real polymorphism.
- `Any` is a boundary tool only, narrowed immediately. `ANN401` is globally ignored just for the container/facade indirection — don't lean on it elsewhere.

## Lazy imports

Optional dependencies (redis, jwt, boto3, azure, google, websockets, …) are imported **inside** the function or factory that needs them, never at module top level. This keeps `import arvel` fast and the optional extras truly optional. The many `PLC0415` per-file ignores in `pyproject.toml` mark these intentional local imports.

## Subsystem uniformity

Config → manager → driver protocol → provider (→ facade). New subsystems mirror the existing ones (cache, queue, mail, storage, …). See [extending](extending.md).

## Provider phases

`register()` is sync and binding-only. `boot()` is async and does I/O. `shutdown()` runs in reverse order and logs (doesn't raise on) teardown errors. Never open connections in `register()`.

## Laravel-parity naming

Some DSLs intentionally use camelCase to match Laravel (`withoutOverlapping`, `onOneServer`, `dailyAt`, `__()`, `__choice()`). These are scoped `N802`/`N807`/`N818` exceptions in `pyproject.toml`, not license to camelCase elsewhere. Public exception names that don't end in `Error` (`ProviderNotFound`, `SearchEngineNotConfigured`) are deliberate `N818` exceptions.

## Comments

Explain **why**, not **what**. No narration, no section banners, no changelog comments, no ticket IDs in code. One useful line beats a paragraph. See `.cursor/rules/111-comment-style.mdc`.

## Suppressions

The bar for any `# noqa` / `# type: ignore[code]` / `# nosec` is: specific code, real reason, narrowest scope, and a rationale comment matching the existing `per-file-ignores` style. Prefer a scoped `per-file-ignores` entry over inline noise. Never loosen tool config to pass a gate.

## Git & releases

- **Conventional Commits** — Release Please derives versions and the changelog from them.
- Branch prefixes: `feat/`, `fix/`, `docs/`, `refactor/`, `test/`, `chore/`, `ci/`.
- Keep PRs under ~400 lines where practical; link the issue.
- Releases are automated via Release Please → GitHub Release → PyPI Trusted Publishing, signed with Sigstore and shipped with a CycloneDX SBOM. Tags use the `arvel-vX.Y.Z` prefix.

## Public API additions

A new public symbol needs: re-export from the package `__init__.py`, a test that imports it via the public path, and a docstring that explains intent.

## See also

- [Quality gates](quality-gates.md) · [Extending](extending.md) · [Repo & build](repo-and-build.md)
