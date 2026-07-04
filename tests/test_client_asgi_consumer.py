"""Consumer-path demonstration (spec 07 test plan): a real in-process ASGI app, driven through
``Http`` via ``httpx.ASGITransport`` — retry against a flaky endpoint, then the same call path
faked with ``Http.fake`` (no network either way, but exercised through the real request/response
machinery — retries, the ``ClientResponse`` wrapper, and the fake transport swap)."""

from __future__ import annotations

from typing import Any

import httpx

from arvel.client import Client

_ATTEMPTS = {"count": 0}


async def _flaky_asgi_app(scope: Any, receive: Any, send: Any) -> None:
    """502s on the first two hits to /orders, then 200s — a real ASGI app, not a mock handler."""
    assert scope["type"] == "http"
    _ATTEMPTS["count"] += 1
    if _ATTEMPTS["count"] < 3:
        await send({"type": "http.response.start", "status": 502, "headers": []})
        await send({"type": "http.response.body", "body": b""})
        return
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": b'{"order_id": 42}'})


async def test_retry_against_a_real_asgi_app_succeeds_on_the_third_attempt() -> None:
    _ATTEMPTS["count"] = 0
    client = Client(transport=httpx.ASGITransport(app=_flaky_asgi_app))
    response = await client.retry(3, 0).get("http://orders.test/orders")
    assert response.status() == 200
    assert response.json("order_id") == 42
    assert _ATTEMPTS["count"] == 3


async def test_the_same_call_path_under_http_fake_hits_no_network_at_all() -> None:
    client = Client(transport=httpx.ASGITransport(app=_flaky_asgi_app))
    with client.fake({"http://orders.test/*": client.response(body={"order_id": 99}, status=200)}):
        response = await client.retry(3, 0).get("http://orders.test/orders")
        assert response.status() == 200
        assert response.json("order_id") == 99
        client.assert_sent(lambda r: r.url == "http://orders.test/orders")
