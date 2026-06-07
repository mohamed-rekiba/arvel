"""Performance + memory benchmarks for the Reverb broadcasting subsystem.

Budgets:

- publish-to-subscribe local fan-out p99 latency ≤ 5 ms
- resident memory ≤ 64 MiB for 1000 connections / 100 channels

Run: ``uv run python benchmarks/bench_reverb.py``

Exits 0 on PASS for all three budgets (publish p99, RSS delta, tracemalloc
heap delta), 1 on FAIL. The CI ``bench-reverb`` and ``bench-tracemalloc``
jobs are hard gates.

Memory unit notes:

- ``resource.getrusage(RUSAGE_SELF).ru_maxrss`` returns kilobytes on Linux
  and bytes on macOS/BSD. ``_ru_maxrss_to_mib`` normalises both to MiB.
- ``tracemalloc`` reports Python-heap allocations in bytes; portable across
  platforms.
"""

from __future__ import annotations

import asyncio
import platform
import resource
import statistics
import sys
import time
import tracemalloc

from arvel.broadcasting.config import ReverbConfig
from arvel.reverb.server import ReverbServer

NFR_PUBLISH_P99_MS = 5.0
NFR_MEMORY_MIB = 64
NFR_CONNECTIONS = 1000
NFR_CHANNELS = 100

# Byte-granular Python-heap budget for the same scenario. Conservative
# ceiling — looser than NFR_MEMORY_MIB because tracemalloc captures heap-only
# allocations, not the OS-level RSS picture.
TRACEMALLOC_BUDGET_MIB = 96


class _QueueSubscriber:
    """Minimal in-memory subscriber — just enqueues frames so publish() awaits cheaply."""

    __slots__ = ("frames",)

    def __init__(self) -> None:
        self.frames: list[str] = []

    async def send(self, frame: str) -> None:
        self.frames.append(frame)


async def _bench_publish_p99_latency_async(iterations: int) -> list[float]:
    server = ReverbServer(config=ReverbConfig(app_id="b", key="b", secret="b"))  # noqa: S106 — benchmark fixture, not a credential
    sub = _QueueSubscriber()
    server.channels.subscribe("bench-channel", sub)

    samples: list[float] = []
    # Warm-up: 50 publishes to settle import + asyncio housekeeping.
    for _ in range(50):
        await server.channels.publish("bench-channel", "warm", {"i": 0})
    sub.frames.clear()

    for i in range(iterations):
        t0 = time.perf_counter()
        await server.channels.publish("bench-channel", "tick", {"i": i})
        samples.append((time.perf_counter() - t0) * 1000.0)  # ms
    return samples


def bench_publish_p99_latency(iterations: int = 1000) -> list[float]:
    """Return per-call publish latency samples in milliseconds."""
    return asyncio.run(_bench_publish_p99_latency_async(iterations))


def _ru_maxrss_to_mib(ru_maxrss: int) -> float:
    """getrusage returns kilobytes on Linux, bytes on macOS — normalise to MiB."""
    if sys.platform == "darwin":
        return ru_maxrss / (1024 * 1024)
    # Linux + BSD report kilobytes.
    return ru_maxrss / 1024


def bench_resident_memory(connections: int = NFR_CONNECTIONS, channels: int = NFR_CHANNELS) -> int:
    """Return the *incremental* ru_maxrss cost (raw units) of N subs across M channels.

    The 64 MiB budget covers the broadcasting subsystem's marginal memory cost,
    not the absolute process size (which includes the Python runtime and all of
    arvel's imports). We sample ru_maxrss before allocating the server +
    subscribers, again after, and return the non-negative delta.
    """
    before = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    server = ReverbServer(config=ReverbConfig(app_id="b", key="b", secret="b"))  # noqa: S106 — benchmark fixture, not a credential
    subs: list[_QueueSubscriber] = []
    for i in range(connections):
        sub = _QueueSubscriber()
        subs.append(sub)
        channel = f"bench-channel-{i % channels}"
        server.channels.subscribe(channel, sub)
    assert len(subs) == connections  # keep refs alive
    after = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return max(after - before, 0)


def bench_resident_memory_tracemalloc(
    connections: int = NFR_CONNECTIONS, channels: int = NFR_CHANNELS
) -> int:
    """Return the *incremental* Python-heap cost in bytes for N subs / M channels.

    Companion to ``bench_resident_memory()``. Uses tracemalloc to capture
    byte-granular Python-heap allocations attributable to building the
    broadcasting state, instead of the page-granular RSS high-water mark.

    Returns the absolute delta in bytes; the caller converts to MiB.
    """
    tracemalloc.start()
    baseline = tracemalloc.take_snapshot()
    server = ReverbServer(config=ReverbConfig(app_id="b", key="b", secret="b"))  # noqa: S106
    subs: list[_QueueSubscriber] = []
    for i in range(connections):
        sub = _QueueSubscriber()
        subs.append(sub)
        channel = f"bench-channel-{i % channels}"
        server.channels.subscribe(channel, sub)
    assert len(subs) == connections  # keep refs alive
    after = tracemalloc.take_snapshot()
    diff = after.compare_to(baseline, "lineno")
    total_delta = sum(stat.size_diff for stat in diff)
    tracemalloc.stop()
    return max(int(total_delta), 0)


def _format_p99(samples: list[float], *, label: str, target: float, unit: str) -> tuple[str, bool]:
    p50 = statistics.median(samples)
    p99 = sorted(samples)[max(0, int(len(samples) * 0.99) - 1)]
    pass_ = p99 <= target
    status = "PASS" if pass_ else "FAIL"
    line = (
        f"{label:<40} p50={p50:8.4f}{unit}  p99={p99:8.4f}{unit}  target={target}{unit}  [{status}]"
    )
    return line, pass_


def _format_memory(ru_delta: int, *, label: str, target_mib: int) -> tuple[str, bool]:
    """ru_delta is the *incremental* maxrss after creating server + subs."""
    mib = _ru_maxrss_to_mib(ru_delta)
    pass_ = mib <= target_mib
    status = "PASS" if pass_ else "FAIL"
    line = (
        f"{label:<40} delta_rss={mib:8.2f}MiB  target={target_mib}MiB  "
        f"[{status}]  ({platform.system()} delta raw={ru_delta})"
    )
    return line, pass_


def _format_tracemalloc(byte_delta: int, *, label: str, target_mib: int) -> tuple[str, bool]:
    mib = byte_delta / (1024 * 1024)
    pass_ = mib <= target_mib
    status = "PASS" if pass_ else "FAIL"
    line = (
        f"{label:<40} heap_delta={mib:8.2f}MiB  target={target_mib}MiB  [{status}]  (tracemalloc)"
    )
    return line, pass_


def main() -> int:
    print("Arvel Reverb broadcasting benchmarks\n")
    all_pass = True

    samples = bench_publish_p99_latency(iterations=1000)
    line, ok = _format_p99(
        samples,
        label="ChannelManager.publish (1 sub)",
        target=NFR_PUBLISH_P99_MS,
        unit="ms",
    )
    print(line)
    all_pass = all_pass and ok

    ru_delta = bench_resident_memory(connections=NFR_CONNECTIONS, channels=NFR_CHANNELS)
    line, ok = _format_memory(
        ru_delta,
        label=f"{NFR_CONNECTIONS} conns / {NFR_CHANNELS} channels (RSS)",
        target_mib=NFR_MEMORY_MIB,
    )
    print(line)
    all_pass = all_pass and ok

    heap_delta = bench_resident_memory_tracemalloc(
        connections=NFR_CONNECTIONS, channels=NFR_CHANNELS
    )
    line, ok = _format_tracemalloc(
        heap_delta,
        label=f"{NFR_CONNECTIONS} conns / {NFR_CHANNELS} channels (heap)",
        target_mib=TRACEMALLOC_BUDGET_MIB,
    )
    print(line)
    all_pass = all_pass and ok

    print()
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
