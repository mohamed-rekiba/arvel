# ADR-061 — Reverb benchmark CI job is advisory (`continue-on-error: true`)

**Status**: Accepted
**Date**: 2026-05-19
**Deciders**: Solution Architect (autonomous)

## Context

WI-014 introduces `benchmarks/bench_reverb.py` to measure:

- NFR-013-001 — publish-to-subscribe local fan-out p99 ≤ 5 ms
- NFR-013-003 — resident memory ≤ 64 MiB for 1000 connections / 100 channels

A new CI job `bench-reverb` runs the benchmark on every push to `main`. The question is whether the job should **block merge on budget miss** (hard gate) or **report and continue** (advisory).

## Decision

`bench-reverb` is **advisory**: `continue-on-error: true`, mirrors the existing `benchmark` job (`bench_foundations.py`).

```yaml
- name: Run reverb benchmarks
  run: uv run python benchmarks/bench_reverb.py | tee bench-reverb-output.txt
  continue-on-error: true
```

The script itself still exits non-zero on budget miss — that signal feeds the CI logs and the uploaded artifact. The `continue-on-error: true` only prevents the job's red status from blocking merges.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Hard gate (`continue-on-error: false`) | Forces immediate attention to regressions | Shared GitHub Actions runners are noisy — p99 latency can vary ±30% across runs. False reds will quickly desensitise reviewers and erode trust in the gate. | Rejected for now |
| Advisory + alert on threshold breach via separate workflow | Loud signal without blocking | Adds bot/notification infra not currently in arvel CI; out of scope for WI-014 | Rejected — premature |
| **Advisory** (`continue-on-error: true`) | Captures regressions in CI logs + artifacts; matches existing `benchmark` job; lets us collect baseline first before tightening | Doesn't force action on regression | **Accepted** |
| Skip the benchmark in CI entirely | No flake risk | Loses the regression-detection point of having a benchmark | Rejected |

## Consequences

### Positive
- Consistent with existing `benchmark` job — one policy, easy to understand
- Lets us collect baseline numbers across many commits before debating threshold-tightening
- Zero risk of false-red blocking unrelated PRs

### Negative
- Real regressions can land unnoticed unless reviewers actively check the artifact
- Mitigated by FB-014-001 (file in Stage 6 ops report): after ~30 days of baselines, evaluate whether to promote to a hard gate as part of WI-017 Hardening

### Neutral
- Future Hardening WI (WI-017) is the natural place to tighten this gate, alongside `bench_foundations.py`

## Related

- SAD-014 § 2.4, § 2.5
- PRD-014 FR-014-013, NFR-014-003, NFR-014-004, NFR-014-008
- Existing `benchmark` job in `.github/workflows/ci.yml` (the `bench_foundations.py` runner) — pattern this ADR formalises
