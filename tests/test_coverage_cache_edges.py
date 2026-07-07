"""Coverage-closing behavioral tests for `arvel.cache`: the `_unwrap` non-envelope
passthrough, span-attribute recording on `add`/`pull`/`flexible` when tracing is on,
`flexible`'s sync-callback revalidation path, a still-pending background revalidation
observed via `wait_for_pending_revalidations`, and a revalidation callback that raises
(swallowed, not propagated). Redis-only branches are intentionally not exercised here —
they require a real redis backend, not a fake."""

from __future__ import annotations

import asyncio
from typing import Any

from arvel.cache import CacheManager, CacheRepository, _unwrap
from arvel.telemetry import configure


def _cache() -> Any:
    return CacheManager().driver()


class _FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_unwrap_passes_through_a_non_envelope_tuple_unchanged() -> None:
    # only a 1-tuple is arvel's own envelope; any other tuple shape is returned as-is
    assert _unwrap((1, 2)) == (1, 2)
    assert _unwrap(()) == ()


class _FakeSpanClient:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def set(self, key: str, value: Any, expire: int | None = None, exist: Any = None) -> Any:
        if exist is False and key in self.store:  # NX semantics: only set if absent
            return False
        self.store[key] = value
        return True

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


def _capture_spans() -> Any:
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    configure(exporter=InMemorySpanExporter())
    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


async def test_add_and_pull_record_span_attributes_when_tracing_is_on() -> None:
    exporter = _capture_spans()
    cache = CacheRepository(_FakeSpanClient())

    assert await cache.add("k", "v") is True
    assert await cache.add("k", "v2") is False  # already present: set-if-absent fails

    assert await cache.pull("k") == "v"
    assert await cache.pull("k", "default") == "default"  # already pulled: miss

    adds = [s for s in exporter.get_finished_spans() if s.name == "cache add"]
    assert any(s.attributes["cache.stored"] is True for s in adds)
    assert any(s.attributes["cache.stored"] is False for s in adds)

    pulls = [s for s in exporter.get_finished_spans() if s.name == "cache pull"]
    assert any(s.attributes.get("cache.hit") is True for s in pulls)


async def test_flexible_records_span_state_when_tracing_is_on() -> None:
    exporter = _capture_spans()
    cache = _cache()
    clock = _FakeClock()

    async def compute() -> int:
        return 1

    await cache.flexible("sp-k", (10, 30), compute, clock=clock)  # miss/expired state
    clock.advance(5)
    await cache.flexible("sp-k", (10, 30), compute, clock=clock)  # fresh state
    clock.advance(15)
    await cache.flexible("sp-k", (10, 30), compute, clock=clock)  # stale state
    await cache.wait_for_pending_revalidations()

    states = {
        s.attributes["cache.flexible_state"]
        for s in exporter.get_finished_spans()
        if s.name == "cache flexible"
    }
    assert states == {"miss", "fresh", "stale"}


async def test_flexible_revalidation_accepts_a_sync_callback() -> None:
    cache = _cache()
    clock = _FakeClock()
    calls = {"n": 0}

    def compute() -> int:
        calls["n"] += 1
        return calls["n"]

    assert await cache.flexible("sync-k", (10, 30), compute, clock=clock) == 1
    clock.advance(15)  # past fresh, within stale: triggers a background revalidation
    assert await cache.flexible("sync-k", (10, 30), compute, clock=clock) == 1
    await cache.wait_for_pending_revalidations()
    assert calls["n"] == 2  # the sync callback's non-awaitable result was used directly


async def test_wait_for_pending_revalidations_awaits_a_still_running_task() -> None:
    cache = _cache()
    clock = _FakeClock()

    async def slow_compute() -> str:
        await asyncio.sleep(0.05)
        return "refreshed"

    async def fast_compute() -> str:
        return "seed"

    await cache.flexible("slow-k", (10, 30), fast_compute, clock=clock)
    clock.advance(15)  # stale: kicks off the background revalidation with slow_compute
    await cache.flexible("slow-k", (10, 30), slow_compute, clock=clock)

    assert cache._background_tasks  # the revalidation hasn't finished yet
    await cache.wait_for_pending_revalidations()
    assert not cache._background_tasks

    clock.advance(0)
    assert await cache.flexible("slow-k", (10, 30), fast_compute, clock=clock) == "refreshed"


async def test_flexible_revalidation_error_is_swallowed_not_raised() -> None:
    cache = _cache()
    clock = _FakeClock()

    async def compute() -> str:
        return "seed"

    async def failing_compute() -> str:
        raise RuntimeError("boom")

    await cache.flexible("fail-k", (10, 30), compute, clock=clock)
    clock.advance(15)
    result = await cache.flexible("fail-k", (10, 30), failing_compute, clock=clock)
    assert result == "seed"  # the caller still gets the stale value
    await cache.wait_for_pending_revalidations()  # doesn't re-raise the background failure

    # the guard key was released in `finally`, so a later revalidation can run again
    clock.advance(0)
    again = await cache.flexible("fail-k", (10, 30), compute, clock=clock)
    assert again == "seed"
