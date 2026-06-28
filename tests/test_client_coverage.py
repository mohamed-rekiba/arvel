"""Coverage — the Http client (httpx) verbs + fluent config, via a mock transport."""

from __future__ import annotations

import httpx

from arvel.client import Client, PendingRequest


def _transport() -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, json={"method": request.method}))


async def test_client_verbs() -> None:
    client = Client(transport=_transport())
    assert (await client.get("https://x.test/")).json() == {"method": "GET"}
    assert (await client.post("https://x.test/")).json() == {"method": "POST"}
    assert (await client.put("https://x.test/")).json() == {"method": "PUT"}
    assert (await client.patch("https://x.test/")).json() == {"method": "PATCH"}
    assert (await client.delete("https://x.test/")).json() == {"method": "DELETE"}


async def test_client_fluent_config() -> None:
    client = Client(transport=_transport())
    assert (await client.with_token("tok").get("https://x.test/")).status_code == 200
    assert (await client.with_headers({"X-A": "1"}).get("https://x.test/")).status_code == 200
    assert (await client.base_url("https://x.test").get("/path")).status_code == 200


async def test_pending_request_verbs_and_timeout() -> None:
    pending = PendingRequest(transport=_transport()).timeout(5.0).with_token("t", scheme="Token")
    assert (await pending.get("https://x.test/")).json() == {"method": "GET"}
