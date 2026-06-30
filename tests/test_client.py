"""T4.2 — Http client over httpx (MockTransport — no network)."""

from __future__ import annotations

import httpx

from arvel.client import Client


def _transport(handler: object) -> httpx.MockTransport:
    return httpx.MockTransport(handler)  # type: ignore[arg-type]


async def test_get_returns_httpx_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/users"
        return httpx.Response(200, json=[{"id": 1}])

    client = Client(transport=_transport(handler))
    response = await client.get("https://api.test/users")
    assert isinstance(response, httpx.Response)
    assert response.status_code == 200
    assert response.json() == [{"id": 1}]


async def test_with_token_sets_authorization_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer t0ken"
        return httpx.Response(204)

    client = Client(transport=_transport(handler))
    response = await client.with_token("t0ken").get("https://api.test/me")
    assert response.status_code == 204


async def test_post_json_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(201, json={"created": True})

    client = Client(transport=_transport(handler))
    response = await client.post("https://api.test/items", json={"name": "x"})
    assert response.json() == {"created": True}


async def test_base_url_and_headers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.test/v1/ping"
        assert request.headers["x-app"] == "arvel"
        return httpx.Response(200)

    client = Client(transport=_transport(handler))
    response = (
        await client.base_url("https://api.test/v1").with_headers({"X-App": "arvel"}).get("/ping")
    )
    assert response.status_code == 200


async def test_timeout_is_chainable_from_the_client() -> None:
    # Client.timeout proxies to a PendingRequest (parity with base_url/with_headers/with_token),
    # so `Http.timeout(5).get(...)` works without first calling another builder method.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    client = Client(transport=_transport(handler))
    response = await client.timeout(5).get("https://api.test/ping")
    assert response.status_code == 200
