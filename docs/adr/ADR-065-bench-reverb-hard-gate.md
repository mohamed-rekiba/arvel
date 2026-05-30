# ADR-065 — Promote `bench-reverb` from advisory to hard CI gate

**Status**: Accepted
**Date**: 2026-05-19
**Predecessor**: ADR-061 (bench-reverb advisory)

> **Renumber note** (2026-05-19): This ADR was originally written as `ADR-062`, but ADR-062 was concurrently assigned to `croniter-for-schedule-expressions` (WI-015 Stage 2b). The next free number after WI-015's 062/063/064 was 065; this file was renumbered to resolve the collision. Treat any external reference to `ADR-062 (bench-reverb)` as a reference to this file.

---

## Context

WI-014 added a `bench-reverb` CI job that runs `benchmarks/bench_reverb.py` on every push and PR. It enforces two thresholds in code (5 ms p99 publish-to-subscribe latency, 64 MiB incremental resident memory growth at 1000 connections × 100 channels) but ships with `continue-on-error: true` — so a regression *prints red* without actually blocking the PR.

ADR-061 documented this as intentional: shared GitHub Actions runners are noisy, and we lacked baseline data to set thresholds that wouldn't either (a) constantly flake (too tight) or (b) be useless (too loose).

The deferred-FB document `docs/backlog/017-deferred-from-realtime-hardening.md` slotted this for WI-017 (Hardening), with the explicit action: collect baseline data, compute a 1.5× p99 envelope, then promote the gate.

---

## Decision

Promote `bench-reverb` to a **hard** CI gate at thresholds calibrated to **1.5× the observed local-replay p99**.

Concretely:

1. The existing code-internal NFR thresholds in `bench_reverb.py` (5 ms p99 latency, 64 MiB memory) **stay as the PRD/NFR contract**.
2. The CI gate uses **looser** thresholds derived from a 50-run local-replay calibration (S2.4 script `benchmarks/scripts/calibrate_bench_reverb.py`). The looser CI gate exists to absorb GitHub runner noise without letting any real regression slip past the contract envelope.
3. The `continue-on-error: true` flag is removed from the `bench-reverb` job.
4. A new `bench-tracemalloc` job runs the byte-granular memory measurement (FB-014-002) with its own (initially looser) gate.

---

## Calibration (to be populated during S2 execution)

Run `python benchmarks/scripts/calibrate_bench_reverb.py --runs 50` locally on a quiet machine and record the output here. The script reports:

| Metric | Median | p99 | p99 × 1.5 (proposed CI gate) | Code-internal NFR |
|---|---|---|---|---|
| `publish_to_subscribe_p99_ms` | TBD | TBD | TBD | 5.0 ms |
| `incremental_resident_memory_mib` | TBD | TBD | TBD | 64 MiB |
| `tracemalloc_heap_delta_mib` | TBD | TBD | TBD | (new) |

After calibration, the chosen gate values are committed to:

- `benchmarks/bench_reverb.py` — code-internal NFR thresholds (unchanged at 5 ms / 64 MiB).
- `.github/workflows/ci.yml` — CI gate thresholds (= 1.5× observed p99).
- This ADR — record of the calibration outcome.

---

## Consequences

**Pros**:
- A real broadcasting perf regression now blocks the PR.
- The CI gate is empirically derived, not a guess.
- The calibration script is re-runnable; when we change the bench or migrate runners, we re-calibrate, not re-guess.

**Cons**:
- Shared-runner noise may still cause occasional flakes. Mitigation: the calibration script is re-runnable in <5 min; if flakes become a problem, we re-calibrate (or, as ADR-061 anticipated, migrate to a self-hosted quiet runner).
- The CI gate threshold and the code-internal NFR threshold are now two separate numbers. The discipline is: NFR is the **product contract**, CI gate is the **measurement contract**. They are documented as different things on purpose.

---

## Alternatives considered

1. **Keep advisory** — rejected. We can't claim 1.0.0 stability with an unenforceable perf budget.
2. **Use the NFR thresholds directly as the CI gate** — rejected. Too tight; would flake on noisy runners. (This is what ADR-061 originally feared.)
3. **Migrate to a self-hosted runner immediately** — rejected for this WI. Self-hosted runner setup is operationally heavy (security, maintenance). If 1.5× p99 calibration proves insufficient post-1.0.0, *then* we migrate.
4. **Track perf in a regression DB instead of a gate** — rejected for this WI. Good idea, but a 1.x backlog item. We need a gate first.

---

## Cross-references

- ADR-061 (predecessor)
- FB-014-001 / FB-014-002 (origin)
- `docs/backlog/017-deferred-from-realtime-hardening.md`
- `benchmarks/bench_reverb.py`
- `benchmarks/scripts/calibrate_bench_reverb.py` (new in S2)
- `.github/workflows/ci.yml`
