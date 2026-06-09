# ADR-026: Back Arvon with the `whenever` datetime library

**Status**: Accepted
**Date**: 2026-06-09
**Related**: [SAD-006](../architecture/SAD-006-arvon.md)

## Context

Arvel needs a Carbon-equivalent datetime layer ("Arvon"). The framework enforces
`mypy --strict` and `pyright --strict` with zero warnings, so the backing datetime
library's typing quality is a first-order concern, not an afterthought. We also want
correctness around the naive/aware distinction and good performance.

## Decision

Wrap **`whenever`** (0.10.0) behind the `Arvon` value type.

`whenever` models time with explicit, distinct types (instant / zoned / plain) so the
naive-vs-aware distinction is encoded in the type system rather than left to convention.
It's Rust-backed (fast), ships `py.typed`, and provides cp314 wheels, so it installs on
Arvel's Python 3.14 target without a build toolchain.

Callers never import `whenever` — it lives inside `arvel.support.arvon`. The wrapper is
the only seam, which contains the blast radius of a pre-1.0 dependency.

## Alternatives considered

| Option | Why not |
|---|---|
| **`pendulum`** | Closest Carbon clone and the most familiar API, but historically friction under strict type checkers — fights Arvel's zero-warning gate. |
| **`arrow`** | Fluent but a thin `datetime` wrapper with a weaker typing story; less active maintenance. |
| **stdlib `datetime` + `zoneinfo`** | Zero dependencies, but no fluent/humanize ergonomics — that's the status quo we're replacing, and we'd reimplement a lot by hand. |

## Consequences

**Positive**
- Strict-type clean by construction; aware/naive confusion is hard to express.
- Fast; no measurable overhead beyond the library on common paths.
- One isolated seam to maintain if the dependency's API shifts.

**Negative / trade-offs**
- `whenever` is pre-1.0 (0.10.0) — API may change. Mitigated by the wrapper and pinning.
- A new compiled dependency in the tree (offset by prebuilt cp314 wheels).

**Follow-ups**
- Migrating the global ORM `datetime` cast to return `Arvon` is deferred; Arvon ships an
  opt-in `arvon` cast instead (see SAD-006, Decision 3).
