# Changelog

Arvel is a monorepo. Each published package keeps its own changelog, generated
from [Conventional Commits](https://www.conventionalcommits.org) by
[release-please](https://github.com/googleapis/release-please) — the version,
the date, and the commit links are all derived from history, not edited by hand.

This root file is the entry point: the cross-cutting roadmap lives in
`[Unreleased]` below, and the per-package history lives in each package's own
`CHANGELOG.md`.

## Per-package changelogs

| Package | Changelog |
|---|---|
| `arvel` (core) | [`packages/arvel/CHANGELOG.md`](packages/arvel/CHANGELOG.md) |
| `arvel-permission` | [`packages/arvel-permission/CHANGELOG.md`](packages/arvel-permission/CHANGELOG.md) |
| `arvel-image` | [`packages/arvel-image/CHANGELOG.md`](packages/arvel-image/CHANGELOG.md) |
| `arvel-oauth` | [`packages/arvel-oauth/CHANGELOG.md`](packages/arvel-oauth/CHANGELOG.md) |
| `arvel-search` | [`packages/arvel-search/CHANGELOG.md`](packages/arvel-search/CHANGELOG.md) |
| `arvel-audit` | [`packages/arvel-audit/CHANGELOG.md`](packages/arvel-audit/CHANGELOG.md) |

Packages version independently. A release tags a commit as
`<package>-v<version>` (e.g. `arvel-v0.7.2`) and publishes the matching
distribution to PyPI.

## [Unreleased]

Work in flight toward the `1.0` public-API review. Tracked here until it lands
in a tagged release; individual changes appear in the relevant package
changelog once shipped.

- Recursive tree relations
- Laravel-style validation rules
- Route model binding
- Resource controllers

> The headline goal before `1.0` is a public-API review and stability pass.
