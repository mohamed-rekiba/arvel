"""WI-017 / FR-017-009 — calibrate bench-reverb CI thresholds.

Runs the broadcasting benchmark N times locally, collects the per-run metrics,
and prints the recommended CI gate values (1.5 x observed p99 per ADR-065).

Usage:
    uv run python benchmarks/scripts/calibrate_bench_reverb.py --runs 50

Output goes to:
    stdout — human-readable summary
    benchmarks/scripts/calibration-results.json — machine-readable raw samples

Rerun whenever the bench or runner changes; update ADR-065's table with the
new numbers.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.bench_reverb import (  # noqa: E402  (sys.path adjusted above)
    NFR_CHANNELS,
    NFR_CONNECTIONS,
    bench_publish_p99_latency,
    bench_resident_memory,
    bench_resident_memory_tracemalloc,
)

OUTPUT_JSON = Path(__file__).parent / "calibration-results.json"
CALIBRATION_FACTOR = 1.5


def _p99(samples: list[float]) -> float:
    return sorted(samples)[max(0, int(len(samples) * 0.99) - 1)]


def _run_once() -> dict[str, float]:
    """One full benchmark pass — returns the three numbers we care about."""
    publish_samples = bench_publish_p99_latency(iterations=1000)
    rss_delta_raw = bench_resident_memory(connections=NFR_CONNECTIONS, channels=NFR_CHANNELS)
    heap_delta_bytes = bench_resident_memory_tracemalloc(
        connections=NFR_CONNECTIONS, channels=NFR_CHANNELS
    )
    # bench_resident_memory returns the raw ru_maxrss units; normalize at call site.
    # We keep raw for cross-platform fidelity.
    return {
        "publish_p99_ms": _p99(publish_samples),
        "rss_delta_raw": float(rss_delta_raw),
        "heap_delta_bytes": float(heap_delta_bytes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs",
        type=int,
        default=50,
        help="number of benchmark passes to execute (default: 50)",
    )
    args = parser.parse_args()

    samples: list[dict[str, float]] = []
    print(f"Calibrating bench-reverb over {args.runs} runs...")
    start = time.perf_counter()
    for i in range(args.runs):
        sample = _run_once()
        samples.append(sample)
        print(
            f"  run {i + 1:>3}/{args.runs}: "
            f"publish_p99={sample['publish_p99_ms']:.3f}ms  "
            f"rss_delta_raw={sample['rss_delta_raw']:.0f}  "
            f"heap_delta_mib={sample['heap_delta_bytes'] / (1024 * 1024):.2f}"
        )

    elapsed = time.perf_counter() - start
    print(f"\nCalibration complete in {elapsed:.1f}s.\n")

    publish_p99 = [s["publish_p99_ms"] for s in samples]
    rss_delta = [s["rss_delta_raw"] for s in samples]
    heap_delta = [s["heap_delta_bytes"] for s in samples]

    summary = {
        "runs": args.runs,
        "elapsed_s": elapsed,
        "publish_p99_ms": {
            "median": statistics.median(publish_p99),
            "p99": _p99(publish_p99),
            "max": max(publish_p99),
            "recommended_gate": _p99(publish_p99) * CALIBRATION_FACTOR,
        },
        "rss_delta_raw": {
            "median": statistics.median(rss_delta),
            "p99": _p99(rss_delta),
            "max": max(rss_delta),
            "recommended_gate": _p99(rss_delta) * CALIBRATION_FACTOR,
        },
        "heap_delta_mib": {
            "median": statistics.median(heap_delta) / (1024 * 1024),
            "p99": _p99(heap_delta) / (1024 * 1024),
            "max": max(heap_delta) / (1024 * 1024),
            "recommended_gate_mib": (_p99(heap_delta) / (1024 * 1024)) * CALIBRATION_FACTOR,
        },
        "samples": samples,
    }

    OUTPUT_JSON.write_text(json.dumps(summary, indent=2))

    print("Summary:")
    for metric, stats in summary.items():
        if metric in ("runs", "elapsed_s", "samples"):
            continue
        if isinstance(stats, dict):
            print(f"  {metric}:")
            for k, v in stats.items():
                print(f"    {k}: {v}")

    print(f"\nRaw samples written to: {OUTPUT_JSON}")
    print(
        f"\nRecommended CI gates (= {CALIBRATION_FACTOR} x observed p99):"
        f"\n  publish_p99_ms     {summary['publish_p99_ms']['recommended_gate']:.3f} ms"
        f"\n  rss_delta_raw      {summary['rss_delta_raw']['recommended_gate']:.0f}"
        f"\n  heap_delta_mib     {summary['heap_delta_mib']['recommended_gate_mib']:.2f} MiB"
        "\n\nUpdate ADR-065 with these values, then update the CI gate "
        "thresholds in .github/workflows/ci.yml."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
