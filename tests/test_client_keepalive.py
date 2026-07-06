"""The Http client reuses a keep-alive connection across sequential calls (round H9)."""

from __future__ import annotations

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
    assert http._shared == {}


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
