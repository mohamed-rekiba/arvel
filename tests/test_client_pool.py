"""Http.pool — concurrent requests over one shared connection, ordered results (spec 07 §3)."""

from __future__ import annotations

import httpx

from arvel.client import Client, ClientResponse, TransportFailed


def _transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/boom":
            raise httpx.ConnectError("pool slot failed")
        return httpx.Response(200, json={"path": request.url.path, "method": request.method})

    return httpx.MockTransport(handler)


async def test_pool_returns_ordered_results_for_n_concurrent_requests() -> None:
    client = Client(transport=_transport())
    results = await client.pool(
        lambda pool: [
            pool.get("https://x.test/a"),
            pool.get("https://x.test/b"),
            pool.get("https://x.test/c"),
        ]
    )
    assert len(results) == 3
    assert all(isinstance(r, ClientResponse) for r in results)
    assert [r.json()["path"] for r in results] == ["/a", "/b", "/c"]


async def test_pool_supports_mixed_verbs_and_builders() -> None:
    client = Client(transport=_transport())
    results = await client.pool(
        lambda pool: [
            pool.get("https://x.test/a"),
            pool.as_form().post("https://x.test/b", data={"x": "1"}),
        ]
    )
    assert [r.json()["method"] for r in results] == ["GET", "POST"]


async def test_pool_holds_the_exception_in_its_slot_instead_of_raising() -> None:
    client = Client(transport=_transport())
    results = await client.pool(
        lambda pool: [
            pool.get("https://x.test/a"),
            pool.get("https://x.test/boom"),
            pool.get("https://x.test/c"),
        ]
    )
    assert isinstance(results[0], ClientResponse)
    assert results[0].json()["path"] == "/a"
    assert isinstance(results[1], TransportFailed)  # wrapped — the pool never leaks httpx
    assert isinstance(results[2], ClientResponse)
    assert results[2].json()["path"] == "/c"


async def test_pool_builder_reuse_does_not_leak_config_across_slots() -> None:
    """`pool.as_form()` on one queued call must not silently apply to a sibling call queued off
    the same builder — PendingRequest builders clone (spec 07 §1: "immutable-ish")."""
    client = Client(transport=_transport())
    results = await client.pool(
        lambda pool: [
            pool.get("https://x.test/a"),  # queued first, off the un-mutated builder
            pool.as_form().post("https://x.test/b", data={"x": "1"}),  # mutates a clone, not `pool`
        ]
    )
    assert [r.json()["method"] for r in results] == ["GET", "POST"]
