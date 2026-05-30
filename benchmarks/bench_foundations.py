"""Smoke benchmarks for WI-arvel-001 NFRs.

NFR-001-001  Application boot ≤ 50 ms (empty provider set, p95).
NFR-001-002  Container.make on a singleton ≤ 1 µs (cached, p95).

Run: ``uv run python benchmarks/bench_foundations.py``
"""

from __future__ import annotations

import asyncio
import statistics
import time
from pathlib import Path

from arvel import Application, Container


def bench_boot(iterations: int = 50) -> list[float]:
    samples: list[float] = []
    for _ in range(iterations):
        app = (
            Application.configure(Path.cwd())
            .with_environment("benchmark")
            .with_providers([])
            .create()
        )
        t0 = time.perf_counter()
        asyncio.run(app.boot())
        samples.append((time.perf_counter() - t0) * 1000.0)  # ms
    return samples


def bench_singleton_make(iterations: int = 100_000) -> list[float]:
    class Service:
        def __init__(self) -> None: ...

    c = Container()
    c.singleton(Service)
    c.make(Service)  # warm cache

    samples: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        for _ in range(iterations):
            c.make(Service)
        elapsed = time.perf_counter() - t0
        samples.append(elapsed / iterations * 1_000_000.0)  # µs per call
    return samples


def _summary(label: str, samples: list[float], target: float, unit: str) -> None:
    p50 = statistics.median(samples)
    p95 = sorted(samples)[max(0, int(len(samples) * 0.95) - 1)]
    status = "PASS" if p95 <= target else "FAIL"
    print(
        f"{label:<32} p50={p50:8.3f}{unit}  p95={p95:8.3f}{unit}  target={target}{unit}  [{status}]"
    )


def main() -> None:
    print("Arvel foundations smoke benchmark\n")
    boot_samples = bench_boot()
    _summary("Application.boot (empty)", boot_samples, target=50.0, unit="ms")

    make_samples = bench_singleton_make()
    _summary("Container.make singleton", make_samples, target=1.0, unit="µs")


if __name__ == "__main__":
    main()
