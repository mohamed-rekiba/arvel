"""The Http client reuses a keep-alive connection across sequential calls, and its
per-loop registry follows event-loop lifecycles (no dead-loop reuse, no growth)."""

from __future__ import annotations

import asyncio
import gc

import httpx
import pytest

from arvel.client import Client


def _echo(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"path": request.url.path})


@pytest.mark.asyncio
async def test_sequential_calls_reuse_one_shared_client() -> None:
    http = Client(transport=httpx.MockTransport(_echo))
    try:
        # two sequential requests on the same loop resolve the same keep-alive client
        first = http._shared_client()
        r1 = await http.get("https://example.test/a")
        second = http._shared_client()
        r2 = await http.get("https://example.test/b")
        assert r1.status() == 200 and r2.status() == 200
        assert first is second  # not a fresh AsyncClient per call
        assert not first.is_closed
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_aclose_closes_pooled_clients() -> None:
    http = Client(transport=httpx.MockTransport(_echo))
    await http.get("https://example.test/a")
    client = http._shared_client()
    assert not client.is_closed
    await http.aclose()
    assert client.is_closed
    assert len(http._shared) == 0


def test_registry_drops_entries_for_collected_loops() -> None:
    """id(loop) can be recycled after GC; the registry must not survive its loop."""
    http = Client(transport=httpx.MockTransport(_echo))
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(http.get("https://example.test/a"))
        assert len(http._shared) == 1
    finally:
        loop.close()
    del loop
    gc.collect()
    assert len(http._shared) == 0  # entry died with the loop — no stale client to inherit


@pytest.mark.asyncio
async def test_non_weakrefable_loop_falls_back_to_per_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A host loop type without weakref support can't be cached — per-call, not a crash."""
    import arvel.client as client_mod

    monkeypatch.setattr(client_mod.asyncio, "get_running_loop", lambda: 5)  # int: no weakrefs
    http = Client(transport=httpx.MockTransport(_echo))
    assert http._shared_client() is None
    r = await http.get("https://example.test/a")
    assert r.status() == 200


def test_live_loops_get_distinct_clients() -> None:
    """An AsyncClient is loop-bound; two live loops must never share one."""

    async def _grab(h: Client) -> httpx.AsyncClient:
        client = h._shared_client()
        assert client is not None
        return client

    http = Client(transport=httpx.MockTransport(_echo))
    loop_a = asyncio.new_event_loop()
    loop_b = asyncio.new_event_loop()
    try:
        a = loop_a.run_until_complete(_grab(http))
        b = loop_b.run_until_complete(_grab(http))
        assert a is not b
        loop_a.run_until_complete(a.aclose())
        loop_b.run_until_complete(b.aclose())
    finally:
        loop_a.close()
        loop_b.close()


@pytest.mark.asyncio
async def test_faking_bypasses_the_shared_client() -> None:
    http = Client()
    http.fake()  # blanket fake — every request gets a default stub
    try:
        assert http._shared_client() is None  # fake path swaps transport per call
        r = await http.get("https://example.test/a")
        assert r.status() == 200
    finally:
        http.restore()
